# Personal SaaS Boundary

This branch hardens the application for a single-user SaaS launch posture.

## What is user-scoped

- Followed bloggers: `POST/DELETE/GET /api/me/bloggers`
- Bookmarked tweets: `POST/DELETE/GET /api/me/tweets`
- Durable analysis jobs: `POST/GET /api/me/analysis-jobs`
- Chat-triggered tweet analysis confirmation: preview creates durable jobs with
  `awaiting_confirmation`; confirm dispatches those jobs only for the same user.

Shared market data remains shared: bloggers, tweets, predictions, public
signals, and aggregate analytics. User actions reference those shared rows
through ownership tables instead of duplicating shared data.

## Expensive analysis controls

User-triggered analysis is disabled by default:

```env
USER_ANALYSIS_REQUESTS_ENABLED=false
USER_ANALYSIS_DAILY_LIMIT=10
USER_ANALYSIS_PIPELINE_VERSION=v1
```

When enabled, requests go through Redis-backed fixed-window limits and fail
closed if Redis is unavailable. Jobs are persisted before Celery dispatch, and
dispatch failures are marked as safe `failed` jobs without exposing broker
details.

## Worker path

`app.scheduler.tasks.user_analysis_job_task` runs durable user analysis jobs on
the `analysis` queue. Tweet jobs reuse existing `analysis_results` for the same
pipeline version when available. Blogger jobs reuse cached analyses when there
are no pending tweets; otherwise they call the existing blogger analysis flow.

## Frontend

`/me` is the personal workspace for:

- followed bloggers
- bookmarked tweets
- analysis job status
- submitting blogger analysis jobs

## Verification

Focused backend regression:

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://.../finance_tweets_test'
python -m pytest tests\integration\test_personal_saas_boundaries.py tests\unit\services\test_user_resource_service.py tests\unit\api\test_me_resources.py tests\unit\api\test_shared_read_auth.py tests\unit\core\test_rate_limit.py tests\unit\api\test_me_analysis_jobs.py tests\unit\services\test_analysis_job_service.py tests\unit\scheduler\test_user_analysis_job_task.py tests\unit\agents\test_chat_analysis_confirmation.py tests\unit\agents\test_chat_private_tools.py tests\unit\agents\test_authenticated_memory_context.py tests\unit\agents\test_mem0_nodes.py -q
```

Frontend:

```powershell
cd frontend
npm run lint
npm run build
```
