"""Celery 应用实例 + Beat 定时任务配置。

启动方式：
  Worker:  celery -A app.celery_app worker --loglevel=info --pool=solo
  Beat:    celery -A app.celery_app beat --loglevel=info
  合并:    celery -A app.celery_app worker --beat --loglevel=info --pool=solo
"""
from celery import Celery
from celery.schedules import crontab

import app.core.tracing  # noqa: F401 — configure LangSmith before LangChain imports
from app.core.config import settings

celery = Celery(
    "finance_tweet_analyzer",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# ============================================================
# Celery 基础配置
# ============================================================
celery.conf.update(
    task_serializer=settings.celery_task_serializer,
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    # 任务级别超时（防止 LLM 调用卡死）
    task_soft_time_limit=300,       # 5 分钟软超时（抛 SoftTimeLimitExceeded）
    task_time_limit=360,            # 6 分钟硬杀
    # Worker 并发控制
    worker_concurrency=2,           # LLM I/O 密集，无需大并发
    worker_prefetch_multiplier=1,   # 一次只取一个任务，避免饿死
    # Redis broker 连接韧性（防止 Windows 空闲超时断连）
    broker_connection_retry_on_startup=True,  # 启动时 broker 不可用自动重试
    broker_connection_max_retries=None,       # 无限重试，不放弃
    broker_pool_limit=10,                     # 连接池，避免频繁建连
    broker_heartbeat=30,                      # 30s 心跳保活
    broker_heartbeat_checkrate=2,             # 每 15s 检查一次心跳
    redis_socket_connect_timeout=10,          # 连接超时 10s
    redis_socket_timeout=30,                  # 读写超时 30s
    redis_backend_health_check_interval=30,   # 后端健康检查间隔
    # 任务路由
    task_routes={
        "app.scheduler.tasks.auto_analysis_task": {"queue": "analysis"},
        "app.scheduler.tasks.manual_analysis_task": {"queue": "analysis"},
        "app.scheduler.tasks.prediction_batch_task": {"queue": "prediction"},
        "app.scheduler.tasks.ingest_document_task": {"queue": "ingest"},
        "app.scheduler.tasks.embed_signal_task": {"queue": "embed"},
        "app.scheduler.tasks.backfill_signals_task": {"queue": "embed"},
        "app.scheduler.tasks.scheduled_report_task": {"queue": "report"},
        "app.scheduler.tasks.report_streaming_task": {"queue": "report"},
        "app.scheduler.tasks.scan_due_tracking_task": {"queue": "default"},
        "app.scheduler.tasks.gc_vector_task": {"queue": "default"},
        "app.scheduler.tasks.backfill_search_vector_task": {"queue": "default"},
        "app.scheduler.tasks.scan_blogger_tweets_task": {"queue": "ingest"},
        "app.scheduler.tasks.user_analysis_job_task": {"queue": "analysis"},
        "app.scheduler.tasks.fetch_blogger_tweets_task": {"queue": "ingest"},
    },
    task_default_queue="default",
)

# ============================================================
# Beat 定时调度配置
# ============================================================
celery.conf.beat_schedule = {
    # 自动分析：按配置间隔扫描 pending 推文
    "auto-analysis-periodic": {
        "task": "app.scheduler.tasks.auto_analysis_task",
        "schedule": settings.scheduler_interval_minutes * 60,  # 秒
        "options": {"queue": "analysis"},
    },
    # 预测批量生成：每 N 分钟扫描已分析但未生成预测的结果
    "prediction-batch-periodic": {
        "task": "app.scheduler.tasks.prediction_batch_task",
        "schedule": settings.celery_prediction_interval_minutes * 60,  # 秒
        "options": {"queue": "prediction"},
    },
    # 扫描到期的标的订阅，分发报告生成任务
    "scan-due-tracking": {
        "task": "app.scheduler.tasks.scan_due_tracking_task",
        "schedule": 300,  # 每 5 分钟
    },
    # 清理已删除文档残留的向量
    "gc-vector-daily": {
        "task": "app.scheduler.tasks.gc_vector_task",
        "schedule": crontab(hour=3, minute=0),
    },
    # 回填历史已分析推文的向量化（每 10 分钟处理 15 条，避免 embedding API 过载）
    "backfill-signals-periodic": {
        "task": "app.scheduler.tasks.backfill_signals_task",
        "schedule": 600,  # 每 10 分钟
        "kwargs": {"batch_size": 15},
        "options": {"queue": "embed"},
    },
    # 回填历史分析结果的向量化（每 10 分钟处理 15 条）
    "backfill-analysis-signals-periodic": {
        "task": "app.scheduler.tasks.backfill_analysis_signals_task",
        "schedule": 600,
        "kwargs": {"batch_size": 15},
        "options": {"queue": "embed"},
    },
    # 回填 doc_chunks 的 search_vector（每 5 分钟处理 200 条，全部回填完后自动空转）
    "backfill-search-vector-periodic": {
        "task": "app.scheduler.tasks.backfill_search_vector_task",
        "schedule": 300,
        "kwargs": {"batch_size": 200},
    },
    # 定时抓取博主最新推文
    "scan-blogger-tweets": {
        "task": "app.scheduler.tasks.scan_blogger_tweets_task",
        "schedule": settings.twitter_fetch_interval_minutes * 60,
        "options": {"queue": "ingest"},
    },
}

# 自动发现 tasks 模块
celery.autodiscover_tasks(["app.scheduler"])

# Bind as the default app so @shared_task lookups (from FastAPI process)
# use this Redis-broker app instead of falling back to amqp://guest@127.0.0.1.
celery.set_default()
