from __future__ import annotations

import ipaddress
import json
import os
import socket
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

import httpx

from app.integrations.crypto import SecretResolver, canonical_json, sha256_hex, signature_for
from app.integrations.models import IntegrationConnection, OutboundDelivery


@dataclass(frozen=True)
class DeliveryResult:
    success: bool
    status_code: int | None
    response_hash: str | None
    error_code: str | None = None
    error_detail: str | None = None


class OutboundAdapter(Protocol):
    async def deliver(
        self,
        *,
        connection: IntegrationConnection,
        delivery: OutboundDelivery,
        secret_resolver: SecretResolver,
    ) -> DeliveryResult: ...


def _allowed_hosts() -> set[str]:
    return {
        item.strip().lower()
        for item in os.getenv("INTEGRATION_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    }


def validate_destination_url(url: str) -> str:
    parsed = urlparse(url)
    environment = os.getenv("ENVIRONMENT", "development").lower()
    if parsed.scheme not in ({"https"} if environment == "production" else {"http", "https"}):
        raise ValueError("Integration destinations must use an approved HTTP scheme.")
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Integration destination URL is invalid.")

    host = parsed.hostname.lower()
    if environment == "production":
        allowed = _allowed_hosts()
        if not allowed or host not in allowed:
            raise ValueError("Integration destination host is not allowlisted.")
    elif host not in {"localhost", "127.0.0.1", "::1"}:
        # Development still rejects obviously unsafe metadata/link-local targets.
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
        except socket.gaierror:
            addresses = set()
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_link_local or ip.is_multicast or ip.is_unspecified:
                raise ValueError("Integration destination resolves to an unsafe address.")
    return url


def _bounded_response_hash(content: bytes) -> str:
    return sha256_hex(content[:65536])


def _event_envelope(delivery: OutboundDelivery) -> dict[str, Any]:
    return {
        "id": str(delivery.event_id),
        "type": delivery.event_type,
        "version": "1",
        "tenant_id": str(delivery.tenant_id),
        "correlation_id": delivery.correlation_id,
        "data": delivery.payload,
    }


class SignedWebhookAdapter:
    async def deliver(
        self,
        *,
        connection: IntegrationConnection,
        delivery: OutboundDelivery,
        secret_resolver: SecretResolver,
    ) -> DeliveryResult:
        config = connection.config or {}
        path = str(config.get("path") or "")
        if path.startswith("http://") or path.startswith("https://"):
            return DeliveryResult(False, None, None, "INVALID_PATH", "Webhook path must be relative.")
        target = validate_destination_url(urljoin(connection.base_url.rstrip("/") + "/", path.lstrip("/")))
        envelope = _event_envelope(delivery)
        body = canonical_json(envelope)
        timestamp = str(int(__import__("time").time()))
        secret = secret_resolver.resolve(connection.secret_ref)
        signature = signature_for(secret, timestamp, body)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "freight-platform-backend/1",
            "X-Freight-Event-Id": str(delivery.event_id),
            "X-Freight-Tenant-Id": str(delivery.tenant_id),
            "X-Freight-Timestamp": timestamp,
            "X-Freight-Key-Id": connection.signing_key_id or "default",
            "X-Freight-Signature": signature,
            "X-Correlation-Id": delivery.correlation_id,
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connection.timeout_seconds),
                follow_redirects=False,
            ) as client:
                response = await client.post(target, content=body, headers=headers)
            response_hash = _bounded_response_hash(response.content)
            if 200 <= response.status_code < 300:
                return DeliveryResult(True, response.status_code, response_hash)
            retryable = response.status_code in {408, 409, 425, 429} or response.status_code >= 500
            return DeliveryResult(
                False,
                response.status_code,
                response_hash,
                "REMOTE_RETRYABLE" if retryable else "REMOTE_REJECTED",
                f"Destination returned HTTP {response.status_code}.",
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return DeliveryResult(False, None, None, "NETWORK_RETRYABLE", type(exc).__name__)
        except (RuntimeError, ValueError) as exc:
            return DeliveryResult(False, None, None, "CONFIGURATION_ERROR", str(exc))


class N8nWebhookAdapter(SignedWebhookAdapter):
    """n8n production webhooks use the same signed envelope contract.

    The connection's base URL/path must point to the production webhook URL, never
    the editor-only test URL.  n8n remains an orchestration consumer; it does not
    become the source of freight business authority.
    """


class OdooJson2Adapter:
    async def deliver(
        self,
        *,
        connection: IntegrationConnection,
        delivery: OutboundDelivery,
        secret_resolver: SecretResolver,
    ) -> DeliveryResult:
        config = connection.config or {}
        model = str(config.get("model") or "").strip()
        method = str(config.get("method") or "").strip()
        argument_name = str(config.get("argument_name") or "event").strip()
        if not model or not method or not argument_name:
            return DeliveryResult(
                False,
                None,
                None,
                "CONFIGURATION_ERROR",
                "Odoo JSON-2 model, method and argument_name are required.",
            )

        base = validate_destination_url(connection.base_url.rstrip("/") + "/")
        target = validate_destination_url(urljoin(base, f"json/2/{model}/{method}"))
        api_key = secret_resolver.resolve(connection.secret_ref)
        body_value = {argument_name: _event_envelope(delivery)}
        body = canonical_json(body_value)
        headers = {
            "Authorization": f"bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "freight-platform-backend/1",
            "X-Correlation-Id": delivery.correlation_id,
            "Idempotency-Key": str(delivery.id),
        }
        database = config.get("database")
        if database:
            headers["X-Odoo-Database"] = str(database)

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connection.timeout_seconds),
                follow_redirects=False,
            ) as client:
                response = await client.post(target, content=body, headers=headers)
            response_hash = _bounded_response_hash(response.content)
            if 200 <= response.status_code < 300:
                return DeliveryResult(True, response.status_code, response_hash)
            retryable = response.status_code in {408, 409, 425, 429} or response.status_code >= 500
            detail = "Odoo JSON-2 request failed."
            if response.headers.get("content-type", "").startswith("application/json"):
                try:
                    parsed = response.json()
                    detail = str(parsed.get("message") or parsed.get("error") or detail)[:500]
                except (ValueError, AttributeError, TypeError):
                    pass
            return DeliveryResult(
                False,
                response.status_code,
                response_hash,
                "REMOTE_RETRYABLE" if retryable else "REMOTE_REJECTED",
                detail,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return DeliveryResult(False, None, None, "NETWORK_RETRYABLE", type(exc).__name__)
        except (RuntimeError, ValueError) as exc:
            return DeliveryResult(False, None, None, "CONFIGURATION_ERROR", str(exc))


ADAPTERS: dict[str, OutboundAdapter] = {
    "GENERIC_WEBHOOK": SignedWebhookAdapter(),
    "N8N_WEBHOOK": N8nWebhookAdapter(),
    "ODOO_JSON2": OdooJson2Adapter(),
}


def adapter_for(kind: str) -> OutboundAdapter:
    try:
        return ADAPTERS[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported integration kind: {kind}") from exc
