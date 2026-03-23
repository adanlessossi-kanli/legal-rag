from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str
    embedding_model: str = "text-embedding-3-small"
    llm_model: str = "gpt-4o"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    retrieval_top_k: int = 5
    retrieval_min_score: float = 0.7
    source_text_max_length: int = 200
    vector_search_index: str = "vector_index"
    upload_dir: str = "./uploads"
    cors_origins: str = "http://localhost:3000"
    rate_limit_chat: str = "20/minute"
    rate_limit_upload: str = "5/minute"
    max_history_messages: int = 20
    max_question_length: int = 2000
    openai_max_retries: int = 3
    enable_query_rewriting: bool = True
    log_format: str = "json"

    # Multi-agent
    researcher_summarize_threshold: int = 10000
    summarizer_model: str = "gpt-4o-mini"
    summarizer_max_length: int = 500

    # Security
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15
    enable_csp: bool = True

    # Pagination
    default_page_size: int = 20
    max_page_size: int = 100

    # Redis cache
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600
    cache_enabled: bool = True

    # Hybrid search + reranking
    enable_hybrid_search: bool = True
    keyword_search_limit: int = 10
    enable_reranking: bool = True
    rerank_model: str = "gpt-4o-mini"

    # Context Engine
    enable_context_engine: bool = True
    planner_model: str = "gpt-4o"
    planner_timeout: int = 15
    default_namespace: str = "KnowledgeStore"

    # Ingestion queue
    ingestion_max_retries: int = 3
    ingestion_retry_delay_seconds: int = 30

    # Circuit breaker
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 30

    # Audit log
    enable_audit_log: bool = True

    # Document versioning
    enable_document_versioning: bool = True
    max_document_versions: int = 10

    # CSRF
    enable_csrf_protection: bool = True
    csrf_trusted_origins: str = "http://localhost:3000"

    # MongoDB
    mongodb_host: str = "localhost"
    mongodb_port: int = 27017
    mongodb_client_id: str = ""
    mongodb_client_secret: str = ""
    mongodb_db: str = "legal_rag"
    mongodb_options: str = ""

    # File serving
    file_token_expiry_seconds: int = 300

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
