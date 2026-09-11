"""Re-analyse historical commercial tweets with claim-level attribution."""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.core.deps import SessionLocal
from app.models.analysis import AnalysisResult
from app.models.tweet import Tweet
from app.services.analysis_service import analyze_single_tweet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        tweet_ids = list(
            db.execute(
                select(Tweet.id)
                .join(AnalysisResult, AnalysisResult.tweet_id == Tweet.id)
                .where(
                    AnalysisResult.analysis_type == "tweet_analysis",
                    AnalysisResult.result["is_sponsored"].as_boolean().is_(True),
                )
                .order_by(Tweet.published_at.asc())
                .limit(max(1, args.limit))
            ).scalars()
        )
        print(f"commercial_tweets={len(tweet_ids)}")
        completed = 0
        failed = 0
        for tweet_id in tweet_ids:
            result = analyze_single_tweet(db, str(tweet_id))
            if result.get("analyzed"):
                completed += 1
                print(f"reanalyzed={tweet_id}")
            else:
                failed += 1
                print(f"failed={tweet_id} result={result}")
        print(f"completed={completed} failed={failed}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
