# Finance Tweet Analyzer

面向个人投资研究者的 Twitter 投资情报工作台。产品聚焦四件事：管理信息源、持续采集推文、提取可验证的投资信号、基于真实证据问答。

## 核心页面

- 今日：按研究范围聚合最新情报主题、风险和证据。
- 信息源：新增、关注、暂停抓取 Twitter 博主，并查看其历史内容与预测表现。
- 关注：维护关注标的，查看近期情报、方向变化和风险提醒。
- 助手：查询正式关注关系、结构化业务数据及 ES + Milvus 混合检索证据。
- 设置：账户与研究范围入口。

## 数据流程

```text
Twitter profile/tweets
        │
        ├─ PostgreSQL: 博主、原始推文、媒体元数据
        ├─ MinIO: 推文原始图片
        └─ Celery outbox
             ├─ 图片识别
             ├─ Supervisor 分类与文本/风险分析
             ├─ 预测提取与公开行情校验
             ├─ 情报主题投影
             └─ RAG 分块
                    ├─ Elasticsearch: BM25/字段加权检索
                    └─ Milvus: 1024 维语义向量检索

用户问题 → 窄路由选工具 → PG/ES/Milvus 召回 → RRF → rerank → 证据约束回答
```

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Next.js 15、React 19、TypeScript |
| API | FastAPI、Pydantic v2、JWT |
| Agent | LangGraph、LangChain、OpenRouter |
| 异步任务 | Celery、Redis |
| 主数据库 | PostgreSQL、Alembic、psycopg v3 |
| 关键词检索 | Elasticsearch 8、IK 分词 |
| 向量检索/记忆 | Milvus/Zilliz、mem0 |
| 对象存储 | MinIO |
| Embedding / Rerank | DashScope `text-embedding-v4` / `qwen3-rerank` |

## 本地启动

复制 `.env.example` 为 `.env`，至少配置：

- `DATABASE_URL`，使用 `postgresql+psycopg://`。
- `REDIS_URL`、`CELERY_BROKER_URL`、`CELERY_RESULT_BACKEND`。
- `OPENROUTER_API_KEY`、`DASHSCOPE_API_KEY`、`JWT_SECRET_KEY`。
- ES、Milvus、MinIO 连接参数。

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Windows Worker：

```bash
uv run celery -A app.celery_app worker --pool=solo -Q analysis,prediction,ingest,vision,embed,default -l info
uv run celery -A app.celery_app beat -l info
```

前端：

```bash
cd frontend
npm install
npm run dev
```

生产服务器可统一管理：

```bash
bash scripts/manage.sh start
bash scripts/manage.sh status
bash scripts/manage.sh health
bash scripts/manage.sh stop
```

## 验证

```bash
uv run pytest -q
uv run python scripts/evaluate_chat_tool_routing.py
cd frontend && npm run build
```

API 文档在后端启动后访问 `/docs`。
