"""Add claim-level sponsorship attribution and performance eligibility.

Revision ID: 0035_claim_sponsor
Revises: 0034_prediction_contract
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0035_claim_sponsor"
down_revision: str | None = "0034_prediction_contract"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "instrument_claims",
        sa.Column(
            "sponsor_relation",
            sa.String(16),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "instrument_claims",
        sa.Column(
            "performance_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "instrument_claims",
        sa.Column("performance_exclusion_reason", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_instrument_claims_sponsor_relation",
        "instrument_claims",
        ["sponsor_relation"],
    )
    op.create_index(
        "ix_instrument_claims_performance_eligible",
        "instrument_claims",
        ["performance_eligible"],
    )

    # Existing commercial tweets used a tweet-level flag, so their individual
    # claims remain conservative until the source tweet is re-analysed with the
    # new attribution contract. Non-commercial author stances can be backfilled
    # deterministically without another model call.
    op.execute(
        """
        UPDATE instrument_claims AS claim
        SET sponsor_relation = CASE
            WHEN COALESCE(analysis.result->>'is_sponsored', 'false') = 'true'
                THEN 'unclear'
            ELSE 'none'
        END
        FROM analysis_results AS analysis
        WHERE analysis.id = claim.analysis_result_id
        """
    )
    op.execute(
        """
        UPDATE instrument_claims
        SET performance_eligible = (
                downstream_eligible = true
                AND opinion_source = 'author'
                AND claim_type IN ('recommendation', 'prediction', 'opinion')
                AND direction IN ('bullish', 'bearish', 'neutral')
                AND sponsor_relation IN ('none', 'unrelated')
            ),
            performance_exclusion_reason = CASE
                WHEN downstream_eligible = false THEN 'instrument_not_verified'
                WHEN opinion_source <> 'author' THEN 'opinion_not_author'
                WHEN claim_type NOT IN ('recommendation', 'prediction', 'opinion')
                    THEN 'claim_type_not_stance'
                WHEN direction NOT IN ('bullish', 'bearish', 'neutral')
                    THEN 'direction_not_comparable'
                WHEN sponsor_relation = 'direct' THEN 'sponsor_related'
                WHEN sponsor_relation = 'unclear' THEN 'sponsor_relation_unclear'
                ELSE NULL
            END
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_instrument_claims_performance_eligible",
        table_name="instrument_claims",
    )
    op.drop_index(
        "ix_instrument_claims_sponsor_relation",
        table_name="instrument_claims",
    )
    op.drop_column("instrument_claims", "performance_exclusion_reason")
    op.drop_column("instrument_claims", "performance_eligible")
    op.drop_column("instrument_claims", "sponsor_relation")
