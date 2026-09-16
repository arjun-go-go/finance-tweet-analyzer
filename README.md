# Signal · Finance Tweet Analyzer

面向个人投资研究者的 Twitter/X 投资情报工作台。持续采集关注博主的公开内容，将一条推文拆解为**逐标的观点、市场宏观判断、证据、风险与可验证预测**，并使用公开行情完成后续复核。

![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![Next.js 15](https://img.shields.io/badge/Next.js-15-000000?logo=next.js&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-psycopg%203-4169E1?logo=postgresql&logoColor=white)
![LangGraph](https://img.shields.io/badge/Agent-LangGraph-1C3C3C)

## 项目定位

普通舆情工具通常给整条内容打一个“看多/看空”标签，但一条推文可能同时讨论多个标的、引用第三方观点、陈述事实并提示风险。本项目以**投资标的**为分析核心：

- 每个标的独立提取方向、周期、依据、催化因素、风险和失效条件。
- 区分博主本人观点、引用观点、第三方观点、事实提及和商业内容。
- 没有具体标的时，单独提取利率、通胀、流动性、政策、增长和地缘风险等市场判断。
- 只有身份已验证、来源归属明确并满足预测契约的观点，才进入共识与表现统计。

项目当前聚焦个人 Twitter 投资研究，不包含交易执行。已下线的对话助手、私人资料和研究课题不属于当前产品范围。

## 核心功能

### 1. Twitter 信息源采集

- 通过 Twitter Handle 添加博主并获取公开资料。
- 支持普通推文、长推文、回复、引用、转发和 X Article。
- 定时采集可按博主独立启停，重复内容按 Tweet ID 去重。
- 原始文本、关系上下文和处理状态写入 PostgreSQL。

### 2. 图文联合分析

- 推文图片和 X Article 封面归档至 MinIO。
- 视觉模型提取图表文字、关键数字、标的和风险证据。
- 文本、图片、引用关系和同一线程上下文共同进入分析流程。

### 3. 逐标的观点提取

每个标的独立生成结构化结果，包括：

- 方向：看多、看空、中性或无明确方向。
- 周期：短期、中期、长期或未说明。
- 观点类型：建议、预测、意见、风险提示、事实、新闻、复盘或仅提及。
- 判断依据、催化条件、风险因素、入场条件和失效条件。
- 观点来源、商业关联、提取置信度及是否允许进入下游统计。

### 4. 标的身份校验

当前覆盖 A 股、港股、美股、WTI 原油、XAU 黄金和加密货币：

| 市场 | 主要校验数据源 |
|---|---|
| A 股、港股 | AKShare |
| 美股及全球代码映射 | SEC EDGAR、OpenFIGI v3 |
| 加密货币 | Binance `exchangeInfo` |
| WTI 原油 | U.S. EIA Open Data |
| XAU 黄金 | Binance PAXG/USDT 代理行情 |

未验证或身份冲突的标的仍保留原始证据，但默认不进入多空共识、预测成绩与排行。

### 5. 预测与自动复核

- 将可验证观点转换为带来源、方向、时间范围和失效条件的预测契约。
- 根据各市场交易日、开收盘时间和已完成行情自动选择基准价格。
- 到期后使用公开行情判定结果，并保留数据源、价格窗口和规则版本。
- 管理员可以修正同名标的、排除无效预测，所有操作保留审计记录。

### 6. 检索与索引基础设施

- Elasticsearch 8 + IK：BM25、字段权重、时间范围和来源过滤。
- Milvus/Zilliz：推文和分析结果的 1024 维语义向量。
- 四路召回：原始推文、分析结果、结构化数据和 BM25。
- RRF 融合后使用 DashScope `qwen3-rerank` 重排，并按来源类型控制配额。
- PostgreSQL `index_jobs` 记录索引状态，支持失败重试、对账和 ES alias 切换。

## 核心页面

| 页面 | 路径 | 作用 |
|---|---|---|
| 动态 | `/` | 按时间查看推文原文、标的摘要和市场判断；点击后在右侧查看完整分析 |
| 博主 | `/sources` | 新增、关注、取消关注、启停采集并查看处理状态 |
| 博主详情 | `/sources/[handle]` | 查看单个博主的历史内容、观点与预测表现 |
| 标的 | `/watch` | 浏览已验证标的以及当前用户关注的标的 |
| 标的详情 | `/watch/[id]` | 查看相关博主观点、风险、证据和验证结果 |
| 设置 | `/settings` | 管理账户、研究范围和安全设置 |

预测复核、运行状态、Elasticsearch 管理和检索质量调试位于管理员页面，不属于普通用户主导航。

## 业务流程

```mermaid
flowchart LR
    X[Twitter / X] --> INGEST[采集 Worker]
    INGEST --> PG[(PostgreSQL)]
    INGEST --> OUTBOX[Transactional Outbox]

    OUTBOX --> MEDIA[媒体归档]
    MEDIA --> MINIO[(MinIO)]
    MINIO --> VISION[图片识别]

    OUTBOX --> SUPERVISOR[LangGraph Supervisor]
    VISION --> SUPERVISOR
    SUPERVISOR --> CLAIMS[逐标的观点与市场判断]
    CLAIMS --> REVIEW[跨模型复核与业务校验]
    REVIEW --> VERIFY[标的身份与预测验证]
    VERIFY --> PG

    OUTBOX --> INDEX[索引任务]
    INDEX --> ES[(Elasticsearch)]
    INDEX --> MILVUS[(Milvus / Zilliz)]

    PG --> API[FastAPI]
    ES --> API
    MILVUS --> API
    API --> WEB[Next.js Web]
```

采集完成后，原始推文立即进入检索索引；分析完成后，再写入逐标的观点和分析结果索引。媒体归档、图片识别、文本分析和索引任务通过 Outbox 解耦，避免网络或模型故障丢失任务。

## Agent 与模型分工

所有模型统一通过 OpenRouter 接入，不在业务代码中直接调用不同厂商客户端。

| 角色 | 配置项 | 职责 |
|---|---|---|
| 信号模型 | `SIGNAL_MODEL` | 分类、逐标的提取、风险评估和高频结构化任务 |
| 复核模型 | `REVIEW_MODEL` | 使用不同模型家族独立复核高置信度或关键结果 |
| 仲裁/报告模型 | `REPORT_MODEL` | 关键字段冲突裁决和复杂生成 |
| 视觉模型 | `VISION_MODEL` | 推文图片、财报图表和 X Article 封面解析 |

主要处理模式：

1. Supervisor 对内容分类并选择分析路径。
2. Analysis Agent 按标的提取观点，Risk Agent 提取风险。
3. Model Review Agent 对关键结果进行独立复核。
4. 确定性的业务校验层处理来源归属、赞助关系、标的身份和下游资格。
5. Prediction Agent 只为满足契约的观点生成可验证预测。

业务校验层不是额外的大模型，它使用规则和权威数据源约束模型输出，降低同名标的、引用归属和事实提及造成的误判。

## 数据存储职责

| 存储 | 保存内容 | 是否为事实主库 |
|---|---|---|
| PostgreSQL | 用户、关注关系、博主、原始推文、分析结果、逐标的观点、预测、验证、Outbox 和索引账本 | 是 |
| Redis | Celery broker/result、分布式锁、心跳和短期缓存 | 否 |
| MinIO | 推文图片和 X Article 封面原文件 | 否 |
| Elasticsearch | 面向关键词检索的文本块和分析块 | 否，可重建 |
| Milvus/Zilliz | 面向语义召回的向量与元数据 | 否，可重建 |

公开博主、推文、媒体和分析结果作为共享市场数据采集一次；每个账户只保存自己的博主关注、标的跟踪和提醒关系，避免重复存储公开内容。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Next.js 15、React 19、TypeScript、Noto Sans SC |
| API | FastAPI、Pydantic v2、SQLAlchemy 2、JWT |
| Agent | LangGraph、LangChain、OpenRouter、结构化输出 |
| 异步任务 | Celery、Redis、Transactional Outbox |
| 主数据库 | PostgreSQL、Alembic、psycopg v3 |
| 关键词检索 | Elasticsearch 8、IK 分词器 |
| 向量检索 | Milvus/Zilliz、DashScope `text-embedding-v4` |
| 重排 | DashScope `qwen3-rerank` |
| 对象存储 | MinIO；开发环境可使用本地目录 |
| 可观测性 | Loguru、LangSmith（可选）、运行状态与索引任务后台 |

## 快速开始

### 1. 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+ 与 npm
- PostgreSQL
- Redis
- Elasticsearch 8 + IK、Milvus/Zilliz、MinIO（完整生产链路）

### 2. 获取代码

```bash
git clone https://github.com/arjun-go-go/finance-tweet-analyzer.git
cd finance-tweet-analyzer
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，不要把真实密钥提交到 Git。

### 3. 安装依赖并迁移数据库

```bash
uv sync
uv run alembic upgrade head

cd frontend
npm ci
cd ..
```

`DATABASE_URL` 必须使用 psycopg v3：

```dotenv
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/finance_tweets
```

### 4. 启动后端

```bash
uv run uvicorn app.main:app --reload
```

### 5. 启动 Celery Worker

Linux/macOS：

```bash
uv run celery -A app.celery_app worker \
  -Q analysis,prediction,ingest,embed,vision,default \
  -l info
```

Windows 必须使用 `solo` pool：

```powershell
uv run celery -A app.celery_app worker --pool=solo -Q analysis,prediction,ingest,embed,vision,default -l info
```

另开终端启动定时调度：

```bash
uv run celery -A app.celery_app beat -l info
```

可选监控界面：

```bash
uv run celery -A app.celery_app flower --port=5555
```

### 6. 启动前端

```bash
cd frontend
npm run dev
```

默认地址：

- Web：`http://localhost:3000`
- API：`http://localhost:8000`
- OpenAPI：`http://localhost:8000/docs`
- Flower：`http://localhost:5555`

首次使用时，注册账号后进入“博主”页面添加 Twitter Handle，并开启采集。

## 环境变量

完整模板见 [`.env.example`](.env.example)。核心配置按职责分组：

| 分组 | 主要配置 |
|---|---|
| 数据库 | `DATABASE_URL`、`TEST_DATABASE_URL` |
| Redis/Celery | `REDIS_URL`、`CELERY_BROKER_URL`、`CELERY_RESULT_BACKEND` |
| LLM | `OPENROUTER_API_KEY`、`SIGNAL_MODEL`、`REVIEW_MODEL`、`REPORT_MODEL`、`VISION_MODEL` |
| Embedding/Rerank | `DASHSCOPE_API_KEY` |
| Twitter | `TWITTER_AUTH_TOKEN`、`TWITTER_CT0`、`TWITTER_BEARER_TOKEN` |
| Elasticsearch | `RAG_KEYWORD_BACKEND`、`ELASTICSEARCH_URL`、用户名、密码和索引名 |
| Milvus | `VECTOR_BACKEND`、`MILVUS_URI`、`MILVUS_TOKEN`、`MILVUS_DB_NAME` |
| MinIO | `OBJECT_STORAGE_BACKEND`、`MINIO_ENDPOINT`、Access Key、Secret Key 和 Bucket |
| 身份认证 | `JWT_SECRET_KEY`、`CORS_ALLOWED_ORIGINS`、`ADMIN_USER_IDS` |
| 标的与行情 | AKShare、OpenFIGI、SEC、Binance 和 EIA 相关开关及地址 |
| 自动验证 | `AUTO_VERIFICATION_ENABLED`、验证间隔、批量大小和收益阈值 |

注意：

- `.env` 已被 Git 忽略；不要在 README、Issue 或日志中粘贴真实密钥。
- Redis 的应用缓存、Celery broker 和 result backend 应使用不同 DB 编号。
- `JWT_SECRET_KEY` 在生产环境必须使用足够长的随机值。
- SEC 请求需要在 `SEC_USER_AGENT` 中提供应用名称和联系邮箱。
- Twitter Cookie、CSRF Token 或内部 GraphQL Query ID 失效时，需要重新获取或更新。

## Elasticsearch 初始化

先只读检查即将创建的索引配置：

```bash
uv run python -m app.scripts.es_rag_index_plan
```

确认配置后再显式创建：

```bash
uv run python -m app.scripts.create_es_rag_index
```

索引属于可重建读模型，PostgreSQL 始终是原始事实来源。

## 数据库迁移

```bash
# 应用现有迁移
uv run alembic upgrade head

# 修改模型后生成新迁移
uv run alembic revision --autogenerate -m "description"
```

不要修改已经应用过的历史迁移文件，新变更应新增 migration。

## 验证与测试

测试会执行数据库结构创建和清理，必须显式配置独立测试库，且数据库名以 `_test` 结尾：

```dotenv
TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/finance_tweets_test
```

```bash
uv run pytest tests/

cd frontend
npm run lint
npm run build
```

运行时健康检查：

```bash
curl http://localhost:8000/api/live
curl http://localhost:8000/api/ready
curl http://localhost:8000/api/health
```

`/api/health` 会检查 PostgreSQL、Redis、Celery 心跳、Milvus、MinIO 和 Elasticsearch，并返回外部服务熔断器状态。

## 生产部署

仓库提供 Linux user-level systemd 单元和统一管理脚本。默认 systemd 工作目录为 `/data/finance-tweet-analyzer`；如果部署到其他目录，请先修改 [`deploy/systemd`](deploy/systemd) 中的路径。

```bash
uv sync
uv run alembic upgrade head

cd frontend
npm ci
npm run build
cd ..

bash scripts/install-user-systemd.sh
bash scripts/manage.sh start
bash scripts/manage.sh status
bash scripts/manage.sh health
```

常用运维命令：

```bash
bash scripts/manage.sh restart backend
bash scripts/manage.sh restart frontend
bash scripts/manage.sh restart worker
bash scripts/manage.sh logs backend
bash scripts/manage.sh logs worker
bash scripts/manage.sh stop
```

生产环境会将 analysis、vision、embed、ingest、prediction 和 default 队列拆分为独立 Worker，避免慢模型或图片任务阻塞采集与索引。

## 项目结构

```text
finance-tweet-analyzer/
├─ app/
│  ├─ agents/          # Supervisor、分析、风险、复核与预测 Agent
│  ├─ api/             # FastAPI 路由
│  ├─ core/            # 配置、认证、日志、限流与韧性
│  ├─ models/          # SQLAlchemy 数据模型
│  ├─ rag/             # 分块、Embedding、ES/Milvus 检索与重排
│  ├─ scheduler/       # Celery 任务与分布式锁
│  ├─ schemas/         # Pydantic 输入输出协议
│  ├─ scripts/         # ES 索引与数据维护命令
│  └─ services/        # 业务服务与外部数据源适配
├─ alembic/            # PostgreSQL 迁移
├─ deploy/systemd/     # 生产服务单元
├─ frontend/           # Next.js Web
├─ prompts/            # 版本化 Agent 提示词
├─ scripts/            # 启停、回填、评估和运维脚本
├─ tests/              # 后端测试
├─ .env.example        # 环境变量模板
└─ pyproject.toml      # Python 依赖与项目元数据
```

## 常见问题

### 添加博主后没有新推文

检查 `TWITTER_AUTH_TOKEN`、`TWITTER_CT0`、`TWITTER_BEARER_TOKEN` 和代理配置，并确认该博主的采集状态不是“已暂停”。Twitter 凭据过期时，GraphQL 通常返回 401、403 或空时间线。

### 推文一直停留在处理中

确认 Redis、Celery Beat 和对应队列 Worker 正常运行：

```bash
bash scripts/manage.sh status
bash scripts/manage.sh health
```

采集、图片、分析、索引和预测属于不同队列，只启动默认队列无法完成完整流程。

### Windows Worker 启动失败

Windows 下必须使用 `--pool=solo`，默认 prefork pool 会因 `billiard` 进程模型失败。

### ES 显示 yellow

单节点 Elasticsearch 如果索引配置了副本，主分片可用但副本无法分配时会显示 yellow。单节点环境可将副本数设置为 `0`；生产多节点环境应保留副本。

### Milvus 或 Elasticsearch 没有数据

确认 `FEATURE_RAG_ENABLED=true`，对应 Worker 已消费 `embed`/`default` 队列，并检查 PostgreSQL `index_jobs` 中的状态和错误信息。

## 当前边界

- 本项目分析公开 Twitter/X 内容，不提供下单或资产托管能力。
- 自动验证只覆盖已配置并能取得公开行情的市场和标的。
- 模型输出必须经过业务校验，但仍可能存在提取错误；原始证据始终保留供人工复核。
- Twitter Web GraphQL 属于外部依赖，接口、Feature Flag 和凭据可能发生变化。
- 所有结果仅用于研究与信息整理，不构成投资建议。
