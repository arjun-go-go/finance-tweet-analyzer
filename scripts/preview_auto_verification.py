"""Preview automatic market verification without changing prediction scores."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.deps import SessionLocal
from app.models.prediction import Prediction
from app.services.market_verification_service import preview_prediction_verification


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-open", action="store_true")
    parser.add_argument("--ticker")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        query = select(Prediction).where(Prediction.verdict.is_(None))
        if not args.include_open:
            query = query.where(Prediction.verifiable_at <= now)
        if args.ticker:
            query = query.where(Prediction.ticker == args.ticker.upper())
        rows = list(
            db.execute(query.order_by(Prediction.verifiable_at.asc()).limit(args.limit)).scalars()
        )
        results = [preview_prediction_verification(db, row, as_of=now) for row in rows]
    finally:
        db.close()

    summary: dict[str, int] = {}
    for result in results:
        status = str(result["status"])
        summary[status] = summary.get(status, 0) + 1
    print(json.dumps({"summary": summary, "items": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
