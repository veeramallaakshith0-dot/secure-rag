from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    api_prefix: str = "/api/v1"
    initial_admin_username: str | None = None
    initial_admin_email: str | None = None
    initial_admin_password: str | None = None
    qdrant_path: str = "data/qdrant"
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_timeout_seconds: int = 180
    chunk_size: int = 512
    chunk_overlap: int = 64
    rag_top_k: int = 5
    max_upload_bytes: int = 20 * 1024 * 1024
    ocr_enabled: bool = True
    ocr_language: str = "eng"
    ocr_dpi: int = 150
    public_demo_mode: bool = False
    docs_enabled: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
