"""Validate historical analysis tickers and refresh their downstream projections."""

from __future__ import annotations

import argparse
from copy import deepcopy

from sqlalchemy import delete, select

from app.core.deps import SessionLocal
from app.models.analysis import AnalysisResult
from app.models.prediction import Prediction
from app.services.instrument_resolver import (
    resolve_analysis_tickers,
    verified_ticker_symbols,
)
from app.services.outbox_service import enqueue_outbox_event


def _needs_backfill(result: dict, *, force: bool) -> bool:
    tickers = result.get("tickers") or []
    if not tickers:
        return False
    if force:
        return True
    return any(
        not isinstance(item, dict)
        or "validation_status" not in item
        or "tradable" not in item
        for item in tickers
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Do not enqueue tweet/analysis reindex and intelligence refresh events",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    db = SessionLocal()
    stats = {
        "selected": 0,
        "updated": 0,
        "verified": 0,
        "unverified": 0,
        "rejected": 0,
        "predictions_deleted": 0,
        "refresh_events": 0,
        "ticker_summaries_deleted": 0,
    }

    try:
        query = (
            select(AnalysisResult)
            .where(AnalysisResult.analysis_type == "tweet_analysis")
            .order_by(AnalysisResult.created_at.asc())
        )
        rows = [
            row
            for row in db.execute(query).scalars()
            if _needs_backfill(row.result or {}, force=args.force)
        ]
        if args.limit is not None:
            rows = rows[:args.limit]
        stats["selected"] = len(rows)

        for offset in range(0, len(rows), max(1, args.batch_size)):
            batch = rows[offset:offset + max(1, args.batch_size)]
            resolved_results = resolve_analysis_tickers(
                [deepcopy(row.result or {}) for row in batch]
            )

            for row, resolved in zip(batch, resolved_results, strict=True):
                row.result = resolved
                symbols = verified_ticker_symbols(resolved)
                stats["verified"] += len(symbols)
                stats["unverified"] += sum(
                    1
                    for item in resolved.get("tickers") or []
                    if isinstance(item, dict)
                    and item.get("validation_status") != "verified"
                )
                stats["rejected"] += len(resolved.get("rejected_tickers") or [])

                stale_predictions = delete(Prediction).where(Prediction.analysis_id == row.id)
                if symbols:
                    stale_predictions = stale_predictions.where(
                        Prediction.ticker.not_in(symbols)
                    )
                deleted = db.execute(stale_predictions).rowcount or 0
                stats["predictions_deleted"] += deleted

                row.prediction_status = (
                    "pending"
                    if resolved.get("is_investment_related") and symbols
                    else "skipped"
                )
                stats["updated"] += 1

                if not args.no_refresh:
                    enqueue_outbox_event(
                        db,
                        "tweet.index_requested",
                        {"tweet_id": str(row.tweet_id)},
                    )
                    enqueue_outbox_event(
                        db,
                        "analysis.index_requested",
                        {"analysis_result_id": str(row.id)},
                    )
                    enqueue_outbox_event(
                        db,
                        "intelligence.project_requested",
                        {"analysis_result_id": str(row.id)},
                    )
                    stats["refresh_events"] += 3

            db.commit()
            print(f"已处理 {min(offset + len(batch), len(rows))}/{len(rows)}")

        verified_symbols: set[str] = set()
        for result in db.execute(
            select(AnalysisResult.result).where(
                AnalysisResult.analysis_type == "tweet_analysis"
            )
        ).scalars():
            verified_symbols.update(verified_ticker_symbols(result or {}))

        summaries = list(
            db.execute(
                select(AnalysisResult).where(
                    AnalysisResult.analysis_type == "ticker_summary"
                )
            ).scalars()
        )
        for summary in summaries:
            ticker = str((summary.result or {}).get("ticker") or "").upper()
            if ticker not in verified_symbols:
                db.delete(summary)
                stats["ticker_summaries_deleted"] += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("历史标的验证回填完成")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
