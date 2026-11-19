from datetime import timedelta

from sqlalchemy import select

from app.models.tweet import Tweet
from app.services.analysis_control_service import (
    analysis_backlog,
    analysis_ingest_cutoff,
    resume_analysis_manually,
)
from app.services.analysis_service import analysis_eligible_clause
from app.services.outbox_service import dispatch_pending_outbox_events, enqueue_outbox_event


def test_new_only_defers_backlog_but_dispatches_new_and_unpaid_events(db_session):
    control = resume_analysis_manually(db_session, updated_by="test", include_backlog=False)
    cutoff = analysis_ingest_cutoff(control)
    assert cutoff is not None
    now = cutoff
    older = Tweet(tweet_id="1", author_handle="alice", content="Historical", published_at=now,
                  created_at=now - timedelta(days=1))
    fresh = Tweet(tweet_id="2", author_handle="alice", content="Fresh", published_at=now,
                  created_at=now + timedelta(seconds=1))
    db_session.add_all([older, fresh])
    db_session.flush()
    for tweet in [older, fresh]:
        enqueue_outbox_event(db_session, "tweet.analysis_requested", {"tweet_id": str(tweet.id)})
    enqueue_outbox_event(db_session, "tweet.media_analyze_requested", {"tweet_id": str(older.id)})
    enqueue_outbox_event(db_session, "tweet.index_requested", {"tweet_id": str(older.id)})

    eligible = db_session.scalars(select(Tweet.id).where(
        analysis_eligible_clause(ingested_after=analysis_ingest_cutoff(control)),
    )).all()
    assert eligible == [fresh.id]
    assert analysis_backlog(db_session, control)["held_history"] == 1

    sent = []
    dispatch_pending_outbox_events(db_session, send_task=lambda _task, **kwargs: sent.append(kwargs))
    assert {(task["queue"], tuple(task["args"])) for task in sent} == {
        ("analysis", (str(fresh.id),)), ("embed", ("tweet", str(older.id))),
    }

    resume_analysis_manually(db_session, updated_by="test", include_backlog=True)
    sent.clear()
    dispatch_pending_outbox_events(db_session, send_task=lambda _task, **kwargs: sent.append(kwargs))
    assert {(task["queue"], tuple(task["args"])) for task in sent} == {
        ("analysis", (str(older.id),)), ("vision", (str(older.id),)),
    }
