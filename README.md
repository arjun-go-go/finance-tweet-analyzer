# Signal · 财经博主观点追踪

跟踪你关注的 X 博主，从原文、引用和配图里提取逐标的观点。看清他现在怎么判断、与上次有什么变化，以及判断依据在哪里。

**适合已经有固定信息源、想减少刷时间线的研究者。** 支持 A 股、港股、美股、原油、黄金和加密货币。没有具体标的的宏观判断单独展示。

[功能与界面](#从一条推文开始) · [系统架构](#系统架构) · [本地启动](#本地启动) · [验证与部署](#验证与部署)

## 从一条推文开始

### 关注变化

打开「动态 → 关注变化」，左侧是自己关注的博主近期首次记录、方向变化或原文新增依据，右侧对照本次和前一次的方向、时间、原文摘录和可用配图。短期看空与长期看好不视为反转；不同作者、转载、引用和直接推广也不会混进同一条观点历史。

![关注变化：左侧是逐标的变化，右侧对照前后原文](docs/screenshots/opinion-changes.png)

### 全部动态

保留完整时间线。可按「标的观点」或「市场宏观」在服务端筛选；点击推文顶部的分析入口，即可查看标的方向、依据、风险、预测和引用来源。未分析或无明确投资观点的推文仍保留。

![动态：原始推文与逐标的分析并排](docs/screenshots/activity.png)

### 博主与标的

在「博主」输入 X Handle 添加信息源，管理关注或采集状态。在博主页回顾其观点；在标的页对比不同博主的有效观点和仅供参考的提及。明确且可验证的预测独立进入复核，观点不自动变成预测成绩。

![博主：管理博主关注及采集状态](docs/screenshots/sources.png)

以上截图来自本版实际运行的应用，使用独立测试库的虚构演示数据。

## 系统架构

Next.js 通过 FastAPI 读取原文、分析和关注关系。动态和「关注变化」直接查询 PostgreSQL，采集、图片识别、文本分析和索引由 Celery Worker 异步执行。PostgreSQL 是业务数据的事实源，检索索引可以从它重建。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="diagram/system-architecture/signal-architecture.svg">
  <img alt="Signal 系统架构：Next.js、FastAPI、PostgreSQL、Celery 队列、模型和索引之间的关系" src="diagram/system-architecture/signal-architecture.light.svg">
</picture>

[浅色 PNG](diagram/system-architecture/signal-architecture.light@2x.png) · [深色 PNG](diagram/system-architecture/signal-architecture@2x.png)

### 组件与技术栈

| 组件 | 主要职责 |
| --- | --- |
| Next.js 15 / FastAPI | 提供动态、博主、标的和运行监控；API 负责鉴权、业务查询和分页。 |
| PostgreSQL | 保存推文原文、作者与引用关系、图片元数据、分析结果、逐标的观点、预测和用户关注。Outbox 事件及索引任务状态也保存在这里。 |
| Celery Beat / Redis / Worker | Beat 调度定时采集、验证和补偿任务；Outbox 派发器把已提交事件送进 Redis。Worker 分别消费采集、视觉、分析、索引、预测和通用队列。 |
| MinIO / 本地存储 | 保存归档图片文件；PostgreSQL 保存文件关联和识别结果。 |
| LangGraph / OpenAI | Supervisor 编排分类、逐标的提取、风险分析和跨模型复核；独立视觉任务解析图表与图片证据。 |
| Elasticsearch 8 + IK / Milvus（可换 Chroma） | 分别维护关键词和向量索引。DashScope 提供嵌入与重排；混合检索用于检索调试，动态页不依赖它召回。 |

### 数据如何流动

1. **原文先入库。** 采集 Worker 读取 X 时间线，将正文、长文、引用和媒体信息与待处理事件同事务保存。原文索引立即排队，不等待分析；含图推文进入归档和视觉任务，纯文本直接进入分析队列。见[采集入库](app/services/tweet_service.py)和 [Outbox 派发](app/services/outbox_service.py)。
2. **分析后校验并保存。** Supervisor 先分类，非金融内容直接写入跳过结果；金融内容结合图文证据提取逐标的与宏观观点，按条件复核或仲裁。业务层再核对标的身份、观点归属、商业关联及下游资格。见 [LangGraph 编排](app/agents/supervisor.py)和[分析入库](app/services/analysis_service.py)。
3. **分析结果再派生。** 已保存的原文和分析可以在页面查看。入库后异步更新情报和索引，只有符合下游资格的逐标的观点会生成观点索引。宏观判断仍可在动态页查看；满足预测契约的观点才进入独立的预测验证流程。见[索引和验证任务](app/scheduler/tasks.py)。

暂停 OpenAI 文本或图片分析时，采集、原文入库、图片归档和原文索引仍可运行。管理员恢复时可以选择「仅恢复新增」或补跑历史。

## 本地启动

准备 Python 3.12+、[`uv`](https://docs.astral.sh/uv/)、Node.js、PostgreSQL 和 Redis。先创建 PostgreSQL 数据库。

```bash
git clone https://github.com/arjun-go-go/finance-tweet-analyzer.git
cd finance-tweet-analyzer
cp .env.example .env
uv sync
uv run alembic upgrade head
```

PowerShell 中用 `Copy-Item .env.example .env`。按 [配置模板](.env.example) 填写实际值：

| 必需或按功能启用 | 配置 |
| --- | --- |
| 数据库和任务 | `DATABASE_URL`（使用 `postgresql+psycopg://`）、`REDIS_URL`、`CELERY_BROKER_URL`、`CELERY_RESULT_BACKEND` |
| 登录 | `JWT_SECRET_KEY`、`CORS_ALLOWED_ORIGINS`；用 `ADMIN_USER_IDS` 授权管理员 |
| 文本和图像分析 | `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`SIGNAL_MODEL`、`REVIEW_MODEL`、`REPORT_MODEL`、`VISION_MODEL` |
| X 采集 | 启用 `TWITTER_FETCH_ENABLED` 前配置合法的数据访问方式；目前采集器的限制见 [公开发布检查](docs/x-source-readiness.md) |
| 图片、索引与行情 | 可配置 MinIO、`RAG_KEYWORD_BACKEND`、`VECTOR_BACKEND`、`DASHSCOPE_API_KEY` 和各行情 Provider |

在项目根目录分别启动 API、后台 Worker 和定时任务：

```bash
uv run uvicorn app.main:app --reload --port 8000
uv run celery -A app.celery_app worker -Q analysis,prediction,ingest,vision,embed,default -l info
uv run celery -A app.celery_app beat -l info
```

在 Windows 上给 Worker 加 `--pool=solo`。如需修改 API 地址，在前端配置 `NEXT_PUBLIC_API_URL`，并将前端 Origin 加入后端 CORS 列表。

```bash
cd frontend
npm ci
npm run dev
```

访问 [工作台](http://localhost:3000) 或查看 [API 文档](http://localhost:8000/docs)。

## 验证与部署

后端测试必须使用**独立的 PostgreSQL 数据库**；测试会创建和清理表。将 `TEST_DATABASE_URL` 和测试进程内的 `DATABASE_URL` 指向同一个以 `_test` 结尾的数据库，再执行：

```bash
uv run pytest -q tests/
cd frontend
npm run lint
npm run build
```

部署新版本时先备份数据库并执行 `uv run alembic upgrade head`。Linux 可使用 [systemd 单元](deploy/systemd) 和 [管理脚本](scripts/manage.sh)：

```bash
bash scripts/install-user-systemd.sh
bash scripts/manage.sh start
bash scripts/manage.sh status
bash scripts/manage.sh health
```

升级会保留现有分析开关状态。管理员可从「个人工作台（设置）→ 系统运行监控」暂停模型、仅恢复新入库内容，或明确选择「恢复并补跑」。暂停分析期间，采集、原文入库和图片归档继续。运行监控分别展示暂缓的历史任务和最近 24 小时文本模型用量。

## 数据来源说明

公开发布前，先验证数据来源的授权、长文和媒体覆盖、内容撤除和实际价格，见 [X 数据来源公开发布检查](docs/x-source-readiness.md)。采集配置、访问令牌和业务原文不要提交到仓库。

Signal 用于整理和回看公开观点，分析和验证结果仅供研究参考。
