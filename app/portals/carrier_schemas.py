from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CarrierEvidenceSubmissionIn(BaseModel):
    evidence_type: Literal[
        "AUTHORITY",
        "AUTO_LIABILITY",
        "CARGO",
        "GENERAL_LIABILITY",
        "WORKERS_COMP",
        "SAFETY",
    ]
    identifier: str | None = Field(default=None, min_length=2, max_length=180, exclude=True)
    evidence_document_ids: list[UUID] = Field(min_length=1, max_length=30)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_identifier_for_numbered_evidence(self):
        if self.evidence_type != "SAFETY" and not self.identifier:
            raise ValueError("identifier is required for authority and insurance evidence")
        return self


class CarrierEvidenceReviewIn(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["UNDER_REVIEW", "ACCEPTED", "REJECTED", "SUPERSEDED"]
    reviewer_note: str | None = Field(default=None, max_length=4000)
    authoritative_record_id: UUID | None = None
