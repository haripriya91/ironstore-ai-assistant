from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "IronStore AI Assistant"
    app_env: str = "development"

    openai_api_key: SecretStr
    openai_chat_model: str = "gpt-6-luna"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = Field(default=1536, gt=0)

    pinecone_api_key: SecretStr
    pinecone_index_name: str = "ironstore-knowledge"
    pinecone_index_host: str
    pinecone_namespace: str = "ironstore-v1"

    documents_dir: Path = Path("../documents")
    storage_dir: Path = Path("storage")

    retrieval_k: int = Field(default=6, ge=1, le=30)
    max_tool_calls: int = Field(default=4, ge=1, le=10)
    max_history_messages: int = Field(default=6, ge=0, le=20)
    max_question_characters: int = Field(default=4000, ge=1)

    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @property
    def documents_path(self) -> Path:
        return (BACKEND_DIR / self.documents_dir).resolve()

    @property
    def storage_path(self) -> Path:
        return (BACKEND_DIR / self.storage_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()