from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str
    embedding_model: str = "text-embedding-3-small"
    llm_model: str = "gpt-4o"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    retrieval_top_k: int = 5
    retrieval_min_score: float = 1.5
    source_text_max_length: int = 200
    chroma_persist_dir: str = "./chroma_data"
    upload_dir: str = "./uploads"
    cors_origins: str = "http://localhost:3000"
    api_key: str = ""
    rate_limit_chat: str = "20/minute"
    rate_limit_upload: str = "5/minute"
    max_history_messages: int = 20
    max_question_length: int = 2000
    openai_max_retries: int = 3
    enable_query_rewriting: bool = True
    log_format: str = "json"

    model_config = {"env_file": ".env"}


settings = Settings()
