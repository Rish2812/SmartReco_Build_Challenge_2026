from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Mesh API (all LLM calls go through this)
    mesh_api_key: str = ""
    mesh_base_url: str = "https://api.meshapi.ai/v1"
    mesh_model: str = "openai/gpt-4o-mini"

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 1440

    # Database
    database_url: str = "sqlite:///./smartreco.db"

    # Vector store
    chroma_persist_dir: str = "./chroma_data"

    # Recommendation trigger tuning
    rec_event_threshold: int = 5
    rec_min_refresh_seconds: int = 120

    # Digest email (bonus)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    digest_from_email: str = "noreply@smartreco.local"
    digest_send_hour: int = 15
    digest_send_minute: int = 0


settings = Settings()
