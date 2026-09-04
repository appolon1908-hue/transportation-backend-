from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+asyncpg://freight:freight@localhost:5432/freight"
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_algorithms: str = "RS256"
    tracking_webhook_secret: str = ""

    capability_live_tender_send: bool = False
    capability_live_dispatch_notification: bool = False
    capability_email_live_send: bool = False
    capability_sms_live_send: bool = False
    capability_accounting_live_export: bool = False
    capability_customer_portal_external_access: bool = False
    capability_carrier_portal_external_access: bool = False

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        if self.is_production:
            missing = [
                name
                for name, value in {
                    "OIDC_ISSUER": self.oidc_issuer,
                    "OIDC_AUDIENCE": self.oidc_audience,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(f"Missing required production settings: {', '.join(missing)}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
