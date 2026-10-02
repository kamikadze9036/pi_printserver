from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = ""
    postgres_host: str = "db"
    postgres_db: str = "pi_printserver"
    postgres_user: str = "pi_printserver"
    postgres_password: str = ""
    secret_key: str = Field(min_length=32)
    admin_username: str = "admin"
    admin_password: str = Field(min_length=12)
    cookie_secure: bool = False
    public_origin: str = ""
    session_hours: int = Field(default=12, ge=1, le=168)
    printer_timeout: float = Field(default=5, gt=0, le=60)
    max_print_quantity: int = Field(default=500, ge=1, le=99999)
    default_print_quantity: int = Field(default=1, ge=1)
    reason_required: bool = True
    timezone: str = "Europe/Prague"

    @model_validator(mode="after")
    def validate_config(self):
        ZoneInfo(self.timezone)
        if not self.database_url:
            if not self.postgres_password or self.postgres_password.startswith("change-me"):
                raise ValueError("Configure POSTGRES_PASSWORD before starting")
            self.database_url = URL.create(
                "postgresql+psycopg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                database=self.postgres_db,
            ).render_as_string(hide_password=False)
        if self.default_print_quantity > self.max_print_quantity:
            raise ValueError("Default quantity exceeds maximum")
        if self.secret_key.startswith("change-me") or self.admin_password.startswith("change-me"):
            raise ValueError("Configure SECRET_KEY and ADMIN_PASSWORD before starting")
        return self


@lru_cache
def get_config() -> Config:
    return Config()
