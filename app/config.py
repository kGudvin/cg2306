from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Генератор КП"
    app_secret: str = "change-me-please"
    database_url: str = "sqlite:///./storage/app.db"
    google_client_id: str = ""
    dadata_api_token: str = ""
    dadata_timeout_seconds: float = 7.0
    storage_dir: Path = Path("./storage")
    libreoffice_bin: str = "soffice"
    dev_login_enabled: bool = False
    seed_admin_email: str = "admin@example.com"
    seed_admin_password: str = "change_me"
    beshtau_source_template_path: Path = Path("./КП от Кристины.docx")
    kartas_source_template_path: Path = Path("./КП КАРТАС ШАБЛОН.docx")
    access_token_ttl_minutes: int = 60 * 12
    proposal_retention_days: int = 100
    deletion_warning_days: int = 5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def templates_dir(self) -> Path:
        return self.storage_dir / "templates"

    @property
    def generated_dir(self) -> Path:
        return self.storage_dir / "generated"

    @property
    def previews_dir(self) -> Path:
        return self.storage_dir / "previews"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.templates_dir.mkdir(parents=True, exist_ok=True)
    settings.generated_dir.mkdir(parents=True, exist_ok=True)
    settings.previews_dir.mkdir(parents=True, exist_ok=True)
    return settings
