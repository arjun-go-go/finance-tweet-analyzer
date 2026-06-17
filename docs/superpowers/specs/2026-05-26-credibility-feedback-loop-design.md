# Credibility Feedback Loop - Design Spec

> Sub-spec of `2026-05-26-finance-tweet-analyzer-design.md`. Closes the product loop around the existing `TweetAnalysis` + `TickerSummary` pipeline by adding a Bloggers UI and a manual verification → credibility feedback mechanism.

## Goals

- Surface the existing `/api/bloggers` data on the frontend (list + detail).
- Turn each `TweetAnalysis` into one or more verifiable **predictions** (per ticker).
- Allow human verification of each prediction (correct / partial / incorrect) once the investment horizon has elapsed.
- Maintain a Bayesian-smoothed `credibility_score` that converges to a blogger's real hit rate as samples accumulate.
- Persist full blogger profiles (not just handle/name) and tweets to PostgreSQL.

## Non-Goals

- Automated price-based verification (deferred — table is designed to support it later).
- Sentiment / Credibility / Report sub-agents from the parent spec (separate phase).
- Batch verification UI (single-row verify is enough for MVP).
- Credibility recomputation on a schedule — only happens at verify time.

## Decisions Recap

| Topic | Decision |
|---|---|
| Verification method | Manual labeling via UI buttons |
| Score formula | Bayesian smoothing, α=β=5 |
| Granularity | Per (analysis, ticker) row in a new `predictions` table |
| UI scope | Bloggers list + detail page; verify buttons on prediction cards |
| Verifiable gate | Hard constraint: `verifiable_at = published_at + horizon_days` |
| Verdict values | Three: correct=1.0, partial=0.5, incorrect=0.0 |
| Re-verification | Allowed, overwrites previous verdict; no DELETE endpoint |
| Persistence | Blogger profiles + tweets fully stored in PostgreSQL |
| Confidence filter | Only `is_investment_related=True` AND `confidence >= 0.5` become predictions |
| Dedup | (blogger_handle, ticker, sentiment) within 24h is collapsed to one prediction |
| DB | PostgreSQL for both runtime and tests (no SQLite) |

---

## §1 Data Model

### New table: `predictions`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| analysis_id | UUID FK → analysis_results.id | Source analysis row |
| tweet_id | UUID FK → tweets.id | Denormalized for fast lookup |
| blogger_handle | VARCHAR(128) INDEX | Denormalized; predictions are queried by blogger |
| ticker | VARCHAR(64) INDEX | |
| sentiment | VARCHAR(16) | bullish / bearish / neutral |
| investment_horizon | VARCHAR(16) | short / medium / long / unknown |
| published_at | TIMESTAMP WITH TZ | Copied from tweet, basis for `verifiable_at` |
| verifiable_at | TIMESTAMP WITH TZ INDEX | `published_at + horizon_days[horizon]` |
| verdict | VARCHAR(16) NULL | correct / partial / incorrect / NULL when unverified |
| score | FLOAT NULL | 1.0 / 0.5 / 0.0 / NULL |
| verified_at | TIMESTAMP WITH TZ NULL | |
| verified_by | VARCHAR(64) NULL | "manual" for MVP |
| note | TEXT NULL | |
| created_at | TIMESTAMP WITH TZ | server_default=now() |

Indexes:
- `(blogger_handle, verdict)` — for credibility recompute and pending counts
- `(blogger_handle, ticker)` — for hit-rate-by-ticker on detail page
- `(blogger_handle, ticker, sentiment, published_at)` — for 24h dedup lookup

Horizon → days constant:

```python
HORIZON_DAYS = {"short": 7, "medium": 30, "long": 180, "unknown": 30}
```

### `bloggers` table — schema additions

Add columns:

| Column | Type | Notes |
|---|---|---|
| avatar_url | VARCHAR(512) NULL | |
| profile_updated_at | TIMESTAMP WITH TZ NULL | Set whenever upsert touches profile fields |

Existing `total_predictions` and `correct_predictions` get redefined semantics (no schema change):
- `total_predictions` = count of predictions where `verdict IS NOT NULL` — exposed in API responses as `verified_count`
- `correct_predictions` = SUM(`score`) where `verdict IS NOT NULL` (FLOAT-valued, accumulates 0.5 for partial) — exposed as `correct_sum` internally

Both are recomputed and written within the verify transaction. The DB column names are kept for backwards compatibility with existing migrations; API field names use the clearer `verified_count`/`hit_rate` semantics.

### `credibility_score` formula

Computed at query time (not stored), so it is always consistent with the predictions table:

```
score = (correct_sum + 5) / (total_predictions + 10) * 100
```

- `total_predictions == 0` → returns 50.0 (neutral prior)
- Sample size matters: `(0 + 5)/(0 + 10)*100 = 50`, `(1 + 5)/(1 + 10)*100 ≈ 54.5`, `(7 + 5)/(10 + 10)*100 = 60`

Centralized in `app/services/credibility.py::compute_score(correct_sum, total)`.

---

## §2 API

```
POST /api/tweets/import                       # extended: optional batch-level blogger profile
POST /api/bloggers/upsert                     # NEW: upsert blogger profile only
GET  /api/bloggers                            # extended return shape
GET  /api/bloggers/{handle}                   # NEW: aggregated detail
GET  /api/bloggers/{handle}/predictions       # NEW: filtered predictions list
POST /api/predictions/{id}/verify             # NEW: submit / overwrite verdict
```

### POST /api/tweets/import — extended

Request:

```json
{
  "tweets": [{...}],
  "blogger": {
    "handle": "@btc_master",
    "name": "BTC大师",
    "bio": "10 年加密交易员",
    "followers_count": 50000,
    "market_focus": ["crypto"],
    "avatar_url": "https://..."
  }
}
```

Behavior:
- `blogger` is optional. When present, `upsert_blogger()` runs once before tweets are inserted.
- Each tweet's `author_handle` must equal `blogger.handle` if provided; otherwise 422.
- When `blogger` is omitted, current behavior is preserved (`_ensure_blogger` inserts handle/name only).

### POST /api/bloggers/upsert — new

Body identical to the `blogger` object above. Used when a profile changes but no new tweets arrived.

Implementation: PostgreSQL `INSERT ... ON CONFLICT (handle) DO UPDATE SET ...` via SQLAlchemy `postgresql.insert` to avoid select-then-insert race. Sets `profile_updated_at = now()` on every successful upsert.

Response: full Blogger row.

### GET /api/bloggers — extended

Each item:

```json
{
  "handle": "@btc_master",
  "name": "BTC大师",
  "avatar_url": "...",
  "followers_count": 50000,
  "credibility_score": 72.3,        // Bayesian, computed live
  "verified_count": 15,              // verdict IS NOT NULL
  "pending_count": 8,                // verdict IS NULL (includes both locked and verifiable-but-unlabeled)
  "hit_rate": 0.733                  // raw correct_sum / verified_count, no smoothing; null if verified=0
}
```

Sorted by `credibility_score` desc by default. `?sort=verified_count` allowed.

### GET /api/bloggers/{handle}

Returns:

```json
{
  "handle": "@btc_master",
  "name": "...",
  "bio": "...",
  "avatar_url": "...",
  "followers_count": 50000,
  "market_focus": ["crypto"],
  "profile_updated_at": "...",
  "credibility_score": 72.3,
  "verified_count": 15,
  "pending_count": 8,
  "hit_rate_overall": 0.733,
  "hit_rate_by_sentiment": {"bullish": 0.8, "bearish": 0.5, "neutral": null},
  "top_tickers": [
    {"ticker": "BTC", "verified": 5, "hit_rate": 0.9},
    ...
  ],
  "recent_verified": [/* last 10 verified predictions, same shape as below */]
}
```

`top_tickers`: top 5 by verified count where verified ≥ 1, ordered by hit_rate desc then verified desc.

404 if blogger does not exist.

### GET /api/bloggers/{handle}/predictions

Query params:
- `status`: `pending` | `verified` | `all` (default `all`)
- `ticker`: optional exact match
- `limit`: default 20, max 100
- `offset`: default 0

`status=pending` includes both *not yet verifiable* and *verifiable but unverified*; the frontend reads `verifiable_at` to distinguish.

Each item:

```json
{
  "id": "uuid",
  "ticker": "BTC",
  "sentiment": "bullish",
  "investment_horizon": "short",
  "published_at": "...",
  "verifiable_at": "...",
  "verdict": "correct",
  "score": 1.0,
  "verified_at": "...",
  "verified_by": "manual",
  "note": "...",
  "tweet": {
    "id": "uuid",
    "content": "...",
    "published_at": "..."
  }
}
```

### POST /api/predictions/{id}/verify

Body:

```json
{ "verdict": "correct" | "partial" | "incorrect", "note": "optional string" }
```

Logic (single transaction):
1. Load prediction by id; 404 if missing.
2. If `verifiable_at > now()`, return 400 `{"error": "not_yet_verifiable", "verifiable_at": "..."}`.
3. Map verdict → score: correct=1.0, partial=0.5, incorrect=0.0.
4. Set `verdict`, `score`, `verified_at=now()`, `verified_by="manual"`, `note`. Allowed even if previously verified (overwrite).
5. Recompute `bloggers.total_predictions = COUNT(*) WHERE verdict IS NOT NULL` and `bloggers.correct_predictions = SUM(score) WHERE verdict IS NOT NULL` for `prediction.blogger_handle`.
6. Commit.

Response: updated prediction row.

`credibility_score` is **not** stored — clients receive it from `/api/bloggers*` endpoints which compute live.

### Error contract

| Case | Status | Body |
|---|---|---|
| Verifiable date not reached | 400 | `{"error": "not_yet_verifiable", "verifiable_at": iso}` |
| Prediction id missing | 404 | default FastAPI |
| Blogger handle missing on detail/predictions | 404 | default FastAPI |
| `import` blogger.handle ≠ tweet.author_handle | 422 | default Pydantic |
| Invalid verdict value | 422 | default Pydantic |

---

## §3 LangGraph Flow Changes

### Supervisor graph: add a third node

```
analyze_tweets → aggregate_tickers → generate_predictions → END
```

`SupervisorState` adds:

```python
class SupervisorState(TypedDict):
    tweets: list[dict]
    analyses: list[dict]
    ticker_summaries: list[dict]
    predictions: list[dict]   # NEW
```

### `generate_predictions_node` (pure Python, no LLM)

Inputs: `state["analyses"]` and `state["tweets"]` (need `published_at` from tweets).

Pseudocode:

```python
def generate_predictions_node(state):
    tweet_by_id = {t["id"]: t for t in state["tweets"]}
    out = []
    # In-batch dedup: only collapse when same (handle, ticker, sentiment) AND
    # published_at within 24h of an already-emitted prediction.
    seen_by_key: dict[tuple, datetime] = {}

    # Sort analyses by published_at so older predictions win the dedup slot
    sorted_analyses = sorted(
        state["analyses"],
        key=lambda a: tweet_by_id[a["tweet_id"]]["published_at"],
    )

    for analysis in sorted_analyses:
        if not analysis.get("is_investment_related"):
            continue
        if analysis.get("confidence", 0) < 0.5:
            continue

        tweet = tweet_by_id[analysis["tweet_id"]]
        published_at = tweet["published_at"]
        horizon = analysis.get("investment_horizon", "unknown")
        days = HORIZON_DAYS.get(horizon, 30)
        verifiable_at = published_at + timedelta(days=days)

        for ticker in analysis.get("tickers", []):
            key = (analysis["author_handle"], ticker, analysis["sentiment"])
            prior = seen_by_key.get(key)
            if prior is not None and (published_at - prior) < timedelta(hours=24):
                continue
            seen_by_key[key] = published_at
            out.append({
                # analysis_id is populated by the service layer after insert
                "tweet_id": analysis["tweet_id"],
                "blogger_handle": analysis["author_handle"],
                "ticker": ticker,
                "sentiment": analysis["sentiment"],
                "investment_horizon": horizon,
                "published_at": published_at,
                "verifiable_at": verifiable_at,
            })

    return {"predictions": out}
```

### 24h dedup against DB

In-batch dedup is handled by `seen_by_key` above. For cross-batch dedup, `analysis_service._run_analysis` filters each candidate `(blogger_handle, ticker, sentiment, published_at)` against existing rows whose `published_at` falls within ±24h of the candidate:

```sql
SELECT 1
FROM predictions
WHERE blogger_handle = :handle
  AND ticker = :ticker
  AND sentiment = :sentiment
  AND published_at BETWEEN :pub - interval '24 hours' AND :pub + interval '24 hours'
LIMIT 1
```

The window is symmetric around the candidate's `published_at`, so backfilling an older tweet that overlaps an existing prediction is also deduped. Skipped predictions are logged but not returned as errors.

### Why the node lives in the graph

Predictions are a semantic output of analysis (each analysis declares N predictions it stands behind). Keeping the node in the graph allows future extensions (auto-verification node, prediction merge node) without disturbing the service layer.

### Service layer wiring

`analysis_service._run_analysis` change:
1. Invoke graph (now returns `predictions` in state, each keyed by `tweet_id`).
2. Insert `analysis_results` rows; build `analysis_id_by_tweet_id: dict[str, UUID]` from the freshly inserted rows (each tweet → one `tweet_analysis` row).
3. For each candidate prediction, run the symmetric ±24h dedup query (see above). Keep candidates with no prior; log skipped ones.
4. Set `analysis_id = analysis_id_by_tweet_id[tweet_id]` on surviving candidates.
5. Bulk insert `predictions`.
6. Update tweet statuses to `analyzed`.
7. Single trailing `db.commit()`.

---

## §4 Frontend

### Routes

- `/bloggers` — new list page
- `/bloggers/[handle]` — new detail page

### Navbar update

`Dashboard / 推文分析 / 标的推荐 / 博主排行(新)`

### `/bloggers` list

- Card grid (md:grid-cols-2). Each card:
  - Row 1: avatar (32px circle) + handle + name
  - Row 2: followers, market_focus tags
  - Row 3: large `credibility_score` (e.g. 72.3) with subscript `(n=15)`; tooltip explains Bayesian smoothing
  - Row 4: small badges — `已标注 15` / `待标注 8` / `命中率 73%`
- Sort dropdown: credibility / verified count / followers
- Empty state: "暂无博主，先导入推文"

### `/bloggers/[handle]` detail

Sections top-down:

1. **Header card**: avatar (large) / handle / name / bio / followers / market_focus / `profile_updated_at` ("资料更新于 X 天前")
2. **Stats row**: `BloggerStatsHeader` — credibility_score (大字 + n)、verified count、pending count、overall hit rate
3. **Breakdown row**:
   - Sentiment hit rate: bullish 0.8 / bearish 0.5 / neutral —
   - Top tickers: top 5 chips with mini hit rate
4. **Predictions tabs**: `待标注 (n)` / `已标注 (n)` / `全部` — fetches with `?status=...`
5. **PredictionCard list** within each tab

### `PredictionCard.tsx`

Three visual states keyed off `verifiable_at` and `verdict`:

| State | Condition | Visual |
|---|---|---|
| locked | `verdict === null && verifiable_at > now()` | gray border, lock icon, "还剩 X 天可验证" countdown, no buttons |
| verifiable | `verdict === null && verifiable_at <= now()` | sentiment-colored border, three buttons (`看对了` `部分对` `看错了`) + note textarea |
| verified | `verdict !== null` | verdict badge (green/yellow/red), `verified_at`, note display, hover reveals `重新标注` link that re-opens the verifiable form |

Common header per card: ticker tag, sentiment badge, horizon, published_at, tweet content excerpt (max 3 lines, hover/click expand).

Verify submit:
- POST `/api/predictions/{id}/verify` with `{verdict, note}`
- On success: optimistic update card to `verified` state, refetch blogger header (credibility shifts)
- On 400 `not_yet_verifiable`: surface inline error, re-fetch verifiable_at to refresh countdown

### Dashboard tweak

Add one more stat card to the existing grid: `待标注预测 = sum(predictions.pending_count)`. Click navigates to `/bloggers` (sorted by pending_count desc would be nice — add `?sort=pending_count`).

### API client extension

`frontend/src/lib/api.ts` adds:

```ts
fetchBloggers(params?: { sort?: "credibility" | "verified" | "followers" })
fetchBloggerDetail(handle: string)
fetchBloggerPredictions(handle: string, params?: { status?: "pending"|"verified"|"all"; ticker?: string; limit?: number; offset?: number })
verifyPrediction(id: string, body: { verdict: "correct"|"partial"|"incorrect"; note?: string })
upsertBlogger(profile: BloggerProfile)
```

---

## §5 Consistency, Errors, Tests

### Transactions

- **Verify**: single transaction updates `predictions` row + recomputes/updates `bloggers` counts. Failure rolls back both.
- **Analysis run**: single transaction inserts `analysis_results` + `predictions` + updates `tweets.status`. Existing per-row commits in `_run_analysis` are consolidated to a single trailing `db.commit()`.
- **upsert_blogger**: PostgreSQL `INSERT ... ON CONFLICT (handle) DO UPDATE` via `sqlalchemy.dialects.postgresql.insert`. No select-then-insert race.

### Test infrastructure

PostgreSQL only; SQLite removed.

`tests/conftest.py` rewritten:
- Reads `TEST_DATABASE_URL` env var, defaults to `postgresql+psycopg://postgres:postgres@localhost:5432/finance_tweets_test`.
- Session-scoped fixture creates the schema once via `Base.metadata.create_all(engine)`, drops on teardown.
- Per-test fixture: open a connection, begin an outer transaction, bind a `Session` to it, yield; rollback at teardown for full isolation.
- `client` fixture overrides `get_db` to return the same session.

Local prerequisites:

```bash
createdb finance_tweets_test
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/finance_tweets_test \
  uv run pytest
```

Add a note to `AGENTS.md` and project README.

### Test cases

`tests/test_predictions_generation.py`
- Single analysis with 2 tickers → 2 predictions
- `is_investment_related=False` → 0 predictions
- `confidence < 0.5` → 0 predictions
- Same (handle, ticker, sentiment) twice in one batch → 1 prediction (in-batch dedup)
- Same (handle, ticker, sentiment) within 24h cross-batch → second batch skips (DB dedup)
- Different sentiment for same (handle, ticker) within 24h → both predictions inserted
- `verifiable_at` math: short → +7d, medium → +30d, long → +180d, unknown → +30d

`tests/test_verify_prediction.py`
- 400 when `verifiable_at > now()`
- correct → score=1.0, partial → 0.5, incorrect → 0.0
- Re-verify overwrites verdict and recomputes blogger counts
- Blogger `total_predictions` and `correct_predictions` reflect SUM/COUNT after verify
- 404 for unknown id

`tests/test_credibility.py`
- n=0 → 50.0
- n=1 correct → ≈ 54.55
- n=10 with 7 correct → 60.0
- Mixed verdicts (correct, partial, incorrect) compute correctly via score sum

`tests/test_bloggers_api.py`
- List sorted by credibility desc
- List sort param `verified_count` works
- Detail returns `hit_rate_by_sentiment`, `top_tickers` with correct shape
- Detail returns `recent_verified` (limit 10, ordered desc)
- Predictions list `status=pending` excludes verified, `status=verified` excludes unverified

`tests/test_blogger_upsert.py`
- New handle inserts row with `profile_updated_at` set
- Existing handle updates `name`/`bio`/`followers_count`/`avatar_url` and bumps `profile_updated_at`
- `import` with `blogger` block runs upsert before tweet insert
- `import` where `blogger.handle` ≠ tweet.author_handle returns 422

---

## File Touches

```
finance-tweet-analyzer/
├── alembic/versions/
│   └── XXXX_add_predictions_and_blogger_profile.py   # NEW
├── app/
│   ├── models/
│   │   ├── blogger.py                                 # +avatar_url, +profile_updated_at
│   │   └── prediction.py                              # NEW
│   ├── schemas/
│   │   ├── blogger.py                                 # NEW (BloggerProfile, BloggerListItem, BloggerDetail)
│   │   └── prediction.py                              # NEW (PredictionItem, VerifyRequest)
│   ├── services/
│   │   ├── credibility.py                             # NEW (compute_score, recompute_blogger)
│   │   ├── prediction_service.py                      # NEW (verify, list, dedup-query)
│   │   ├── blogger_service.py                         # NEW (upsert, list, detail aggregation)
│   │   ├── analysis_service.py                        # MOD (insert predictions, single commit)
│   │   └── tweet_service.py                           # MOD (handle blogger block, upsert)
│   ├── agents/
│   │   └── supervisor.py                              # MOD (+generate_predictions_node)
│   └── api/
│       ├── bloggers.py                                # MOD (extend list, +detail, +upsert, +predictions)
│       ├── predictions.py                             # NEW (verify endpoint)
│       ├── tweets.py                                  # MOD (accept blogger block)
│       └── router.py                                  # MOD (mount predictions)
├── frontend/src/
│   ├── app/
│   │   ├── page.tsx                                    # MOD (pending stat card)
│   │   └── bloggers/
│   │       ├── page.tsx                                # NEW (list)
│   │       └── [handle]/page.tsx                       # NEW (detail)
│   ├── components/
│   │   ├── BloggerCard.tsx                             # NEW
│   │   ├── BloggerStatsHeader.tsx                      # NEW
│   │   └── PredictionCard.tsx                          # NEW
│   └── lib/
│       └── api.ts                                      # MOD (4 new helpers)
├── tests/
│   ├── conftest.py                                     # REWRITE (PG only)
│   ├── test_predictions_generation.py                  # NEW
│   ├── test_verify_prediction.py                       # NEW
│   ├── test_credibility.py                             # NEW
│   ├── test_bloggers_api.py                            # NEW
│   └── test_blogger_upsert.py                          # NEW
└── AGENTS.md                                           # MOD (PG test setup note)
```

---

## Open Questions / Future Iterations

- **Auto-verification (Phase 2 of this loop)**: add `auto_verified_at` and `auto_score` columns; nightly job calls a price API, fills suggestions, leaves manual `verdict` authoritative.
- **Pending workbench page** (`/predictions/pending`): cross-blogger queue; defer until manual labeling becomes a regular workflow.
- **Time-decay credibility variant**: λ-decayed score for "current state" view, alongside lifetime Bayesian score. Decide after first round of real labels.
- **Soft-delete on predictions**: not in MVP; if a tweet is deleted upstream, leave predictions for historical accuracy.
