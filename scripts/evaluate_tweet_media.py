"""Report a repeatable quality baseline for the tweet image-analysis pipeline."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from app.core.deps import SessionLocal
from app.models import AnalysisResult, TweetMediaAnalysis, TweetMediaAsset


def evaluate() -> dict:
    db = SessionLocal()
    try:
        analyses = list(db.execute(select(TweetMediaAnalysis)).scalars().all())
        assets = list(db.execute(select(TweetMediaAsset)).scalars().all())
        completed = [row for row in analyses if row.status == "completed" and row.result]
        downloaded_by_tweet: dict[str, int] = defaultdict(int)
        for asset in assets:
            if asset.status == "downloaded":
                downloaded_by_tweet[str(asset.tweet_id)] += 1

        final_rows = list(
            db.execute(
                select(AnalysisResult).where(AnalysisResult.analysis_type == "tweet_analysis")
            ).scalars().all()
        )
        latest_final = {}
        for row in sorted(final_rows, key=lambda item: item.created_at):
            latest_final[str(row.tweet_id)] = row

        consistency = Counter()
        summary_count = evidence_count = image_observation_count = asset_reference_count = 0
        confidence_total = 0.0
        fused_count = 0
        review_items = []
        for row in completed:
            result = row.result or {}
            confidence = float(result.get("confidence") or 0.0)
            confidence_total += confidence
            consistency[str(result.get("text_image_consistency") or "missing")] += 1
            summary_count += bool(result.get("combined_summary"))
            image_observation_count += bool(result.get("images"))
            evidence_count += any(
                image.get("visual_evidence") or image.get("numeric_facts")
                for image in result.get("images", [])
            )
            expected_assets = downloaded_by_tweet.get(str(row.tweet_id), 0)
            referenced_assets = len(result.get("asset_ids") or [])
            asset_reference_count += expected_assets > 0 and referenced_assets == expected_assets
            final = latest_final.get(str(row.tweet_id))
            fused_count += bool(final and (final.result or {}).get("media_summary"))
            if confidence < 0.6 or not result.get("combined_summary") or not result.get("images"):
                review_items.append(
                    {
                        "tweet_id": str(row.tweet_id),
                        "confidence": confidence,
                        "has_summary": bool(result.get("combined_summary")),
                        "image_observations": len(result.get("images") or []),
                    }
                )

        denominator = len(completed) or 1
        return {
            "pipeline": {
                "analysis_total": len(analyses),
                "completed": len(completed),
                "failed": sum(row.status == "failed" for row in analyses),
                "assets_total": len(assets),
                "assets_downloaded": sum(asset.status == "downloaded" for asset in assets),
            },
            "quality": {
                "average_confidence": round(confidence_total / denominator, 3),
                "summary_coverage": round(summary_count / denominator, 3),
                "image_observation_coverage": round(image_observation_count / denominator, 3),
                "evidence_coverage": round(evidence_count / denominator, 3),
                "asset_reference_coverage": round(asset_reference_count / denominator, 3),
                "final_analysis_fusion_coverage": round(fused_count / denominator, 3),
                "text_image_consistency": dict(sorted(consistency.items())),
            },
            "needs_human_review": review_items,
        }
    finally:
        db.close()


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
