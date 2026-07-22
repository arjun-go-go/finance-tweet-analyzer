from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ----- Database -----
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/finance_tweets"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800

    # ----- OpenRouter LLM -----
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    http_proxy: str = ""

    # ----- Models -----
    signal_model: str = "qwen/qwen3.7-max"
    report_model: str = "qwen/qwen3.7-max"

    # ----- LangSmith -----
    langsmith_api_key: str = ""
    langsmith_project: str = "finance-tweet-analyzer"
    langsmith_tracing: bool = False

    # ----- Scheduler -----
    scheduler_enabled: bool = True
    scheduler_interval_minutes: int = 10

    # ----- Redis & Celery -----
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_task_serializer: str = "json"
    celery_prediction_interval_minutes: int = 5

    # ----- Memory compression -----
    compression_threshold: int = 40
    compression_keep_recent: int = 10

    # ----- SQL Agent -----
    sql_max_retries: int = 3
    sql_query_timeout: int = 5000
    sql_allowed_tables: list[str] = [
        "bloggers", "tweets", "predictions", "analysis_results"
    ]

    # ----- Agent safety -----
    agent_recursion_limit: int = 30
    agent_max_tokens_per_turn: int = 100000
    agent_tool_result_max_chars: int = 3000

    # ----- Rate limiting (per user) -----
    rate_limit_rpm: int = 30
    rate_limit_tpd: int = 500000
    auth_rate_limit_attempts: int = 10
    auth_rate_limit_window_seconds: int = 60

    # ----- Multi-session limits -----
    max_sessions_per_user: int = 50
    session_token_budget: int = 500000
    user_daily_token_budget: int = 2000000
    user_daily_token_hard_limit: int = 5000000

    # ----- Circuit breaker -----
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: float = 120.0
    tool_max_retries: int = 3
    tool_backoff_base: float = 2.0

    # ----- JWT Auth -----
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7
    admin_user_ids: list[str] = []

    # ----- HTTP security -----
    cors_allowed_origins: list[str] = ["http://localhost:3000"]

    # ----- RAG / Vector store -----
    vector_backend: str = Field(
        default="chroma",
        validation_alias=AliasChoices("VECTOR_BACKEND", "VECTOR_STORE_BACKEND"),
    )
    chroma_persist_dir: str = "./chroma_db"
    milvus_uri: str = ""
    milvus_token: str = ""
    milvus_db_name: str = "default"
    milvus_collection_prefix: str = "finance_tweet"
    milvus_timeout_sec: float = 30.0

    # ----- Embedding -----
    embedding_provider: str = "dashscope"
    dashscope_api_key: str = ""
    embedding_model: str = "text-embedding-v4"
    embedding_dim: int = 1024
    embedding_batch_size: int = 32
    embedding_timeout_sec: float = 30.0

    # ----- Chunking -----
    chunk_size_document: int = 800
    chunk_overlap_document: int = 100
    chunk_size_analysis: int = 1000
    chunk_size_tweet: int = 0

    # ----- Reranker -----
    reranker_model: str = "qwen3-rerank"
    reranker_top_n: int = 10
    reranker_min_score: float = 0.3
    report_rerank_quota: dict[str, int] = {
        "tweet": 4,
        "document": 3,
        "analysis": 2,
        "structured": 1,
    }

    # ----- RAG retrieval -----
    rag_top_k_per_path: int = 15
    rag_rrf_k: int = 60
    rag_retrieval_timeout_sec: float = 5.0
    rag_bm25_top_k: int = 15
    rag_keyword_backend: str = "elasticsearch"

    # ----- Elasticsearch keyword retrieval -----
    elasticsearch_url: str = ""
    elasticsearch_username: str = ""
    elasticsearch_password: str = ""
    es_rag_index: str = "finance_rag_chunks"
    es_request_timeout_sec: float = 3.0
    es_bulk_chunk_size: int = 500

    # ----- Report generation -----
    report_section_timeout_sec: int = 90
    report_total_timeout_sec: int = 300
    report_section_max_sources: int = 30
    report_section_truncate_by_type: dict[str, int] = {
        "tweet": 1000,
        "document": 1000,
        "analysis": 600,
        "structured": 500,
    }
    report_section_truncate_default: int = 500
    report_synth_max_evidence: int = 12
    report_synth_truncate_default: int = 300
    report_stream_redis_channel_prefix: str = "report_stream"
    report_stream_heartbeat_sec: int = 15
    report_stream_max_wait_sec: int = 300

    # ----- Tracking subscriptions -----
    max_tracked_tickers_per_user: int = 20
    max_followed_bloggers_per_user: int = 20

    # ----- User analysis jobs -----
    user_analysis_requests_enabled: bool = False
    user_analysis_daily_limit: int = 10
    user_analysis_pipeline_version: str = "v1"

    # ----- Document quotas -----
    max_documents_per_user: int = 200
    max_document_size_mb: int = 20
    max_total_size_mb_per_user: int = 500
    allowed_file_extensions: list[str] = [".pdf", ".docx", ".md", ".txt"]

    # ----- URL parsing -----
    url_fetch_timeout_sec: int = 15
    url_blocked_hosts: list[str] = [
        "localhost", "127.0.0.1", "0.0.0.0", "::1",
        "169.254.169.254",
    ]

    # ----- Storage -----
    document_storage_root: str = "./uploads"

    # ----- Twitter API -----
    twitter_auth_token: str = ""
    twitter_ct0: str = ""
    twitter_bearer_token: str = ""

    # ----- Twitter scheduled fetch -----
    twitter_fetch_enabled: bool = False
    twitter_fetch_interval_minutes: int = 60
    twitter_fetch_max_pages: int = 2
    twitter_fetch_batch_size: int = 5

    # ----- mem0 long-term memory (self-hosted OSS mode) -----
    mem0_enabled: bool = True
    mem0_chroma_path: str = "./chroma_mem0_db"
    mem0_history_db_path: str = "./mem0_history.db"
    mem0_top_k: int = 5
    mem0_vector_backend: str = "chroma"
    mem0_milvus_collection: str = "finance_tweet_mem0_memories"
    mem0_milvus_metric_type: str = "COSINE"

    # ----- Debug -----
    debug_mode: bool = False

    # ----- Feature flag -----
    feature_rag_enabled: bool = True

    # ----- Logging -----
    log_level: str = "INFO"
    log_json: bool = False
    log_request_body: bool = False
    log_response_body: bool = False
    log_body_max_bytes: int = 4096
    log_sensitive_keys: list[str] = [
        "password", "passwd", "token", "access_token", "refresh_token",
        "authorization", "api_key", "apikey", "secret", "openrouter_api_key",
        "cookie", "set-cookie",
    ]
    log_skip_paths: list[str] = ["/health", "/api/health", "/docs", "/openapi.json", "/favicon.ico"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("jwt_secret_key")
    @classmethod
    def _validate_jwt_secret(cls, v: str) -> str:
        if not v:
            raise ValueError("JWT_SECRET_KEY must be set (non-empty) in .env")
        return v

    @field_validator("openrouter_api_key")
    @classmethod
    def _validate_openrouter_key(cls, v: str) -> str:
        if not v:
            raise ValueError("OPENROUTER_API_KEY must be set (non-empty) in .env")
        return v

    @field_validator("dashscope_api_key")
    @classmethod
    def _validate_dashscope_key(cls, v: str) -> str:
        if not v:
            raise ValueError("DASHSCOPE_API_KEY must be set (non-empty) in .env")
        return v

    def __repr_args__(self):
        sensitive_fields = {
            "database_url",
            "redis_url",
            "celery_broker_url",
            "celery_result_backend",
            "openrouter_api_key",
            "dashscope_api_key",
            "langsmith_api_key",
            "jwt_secret_key",
            "twitter_auth_token",
            "twitter_ct0",
            "twitter_bearer_token",
            "milvus_token",
            "elasticsearch_password",
        }
        for name, value in super().__repr_args__():
            yield name, "**********" if name in sensitive_fields else value


settings = Settings()
