from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Database
    database_url: str = Field(...)

    # API security
    api_keys: List[str] = Field(default_factory=list)
    cors_origins: List[str] = Field(default_factory=list)

    # GitHub Models
    github_token: str = Field(...)
    github_models_base_url: str = "https://models.github.ai/inference"
    llm_model: str = "openai/gpt-4o-mini"
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dim: int = 1536

    # Confluence
    confluence_base_url: str = ""
    confluence_email: str = ""
    confluence_api_token: str = ""
    confluence_spaces: List[str] = Field(default_factory=list)

    # Retrieval
    top_k: int = 5
    max_question_chars: int = 2000

    @field_validator("api_keys", "cors_origins", "confluence_spaces", mode="before")
    @classmethod
    def _split_csv(cls, v):
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
