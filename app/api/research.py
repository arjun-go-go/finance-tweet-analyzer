from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.deps import get_db
from app.models.user import User
from app.schemas.research import ResearchConclusionCreate, ResearchEvidenceCreate, ResearchMonitorUpdate, ResearchTopicCreate, ResearchTopicResponse, ResearchWorkspaceResponse
from app.services import research_service
from app.services.intelligence_service import build_user_intelligence_feed

router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("/brief")
def get_daily_brief(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items, context = build_user_intelligence_feed(db, user.id, limit=12, window="24h", kind="all")
    return {
        "generated_at": context["generated_at"],
        "context": context,
        "personalized": [item for item in items if item["feed_bucket"] == "personalized"],
        "risks": [item for item in items if item["feed_bucket"] == "market_risk"],
        "discoveries": [item for item in items if item["feed_bucket"] == "discovery"],
    }


@router.get("/opportunities")
def get_research_opportunities(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items, _ = build_user_intelligence_feed(db, user.id, limit=30, window="7d", kind="all")
    researched = {
        ticker
        for topic in research_service.list_topics(db, user.id)
        for ticker in (topic.tickers or [])
    }
    opportunities = []
    for item in items:
        tickers = [ticker for ticker in item["tickers"] if ticker not in researched]
        if item["feed_bucket"] != "discovery" or not tickers:
            continue
        opportunities.append({
            "id": item["id"],
            "title": item["title"],
            "summary": item["summary"],
            "tickers": tickers,
            "importance_score": item["importance_score"],
            "reason": "尚未纳入研究范围，且近期出现了新的市场证据",
        })
        if len(opportunities) >= 6:
            break
    return opportunities


@router.post("/topics", response_model=ResearchTopicResponse, status_code=201)
def create_topic(body: ResearchTopicCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return research_service.create_topic(db, user.id, body)


@router.get("/topics", response_model=list[ResearchTopicResponse])
def list_topics(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return research_service.list_topics(db, user.id)


def _owned(db: Session, user_id: UUID, topic_id: UUID):
    topic = research_service.get_topic(db, user_id, topic_id)
    if not topic:
        raise HTTPException(404, "Research topic not found")
    return topic


@router.get("/topics/{topic_id}", response_model=ResearchWorkspaceResponse)
def get_workspace(topic_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    topic = _owned(db, user.id, topic_id)
    evidence, conclusions = research_service.workspace(db, topic)
    return {"topic": topic, "evidence": [{"id": str(item.id), "evidence_key": item.evidence_key, "source_type": item.source_type, "source_id": item.source_id, "tickers": item.tickers, "author": item.author, "published_at": item.published_at, "excerpt": item.excerpt, "source_url": item.source_url, "sentiment": item.sentiment, "verification_status": item.verification_status, "relevance_score": item.relevance_score} for item in evidence], "conclusions": [{"id": str(item.id), "version": item.version, "conclusion": item.conclusion, "thesis": item.thesis, "counter_evidence": item.counter_evidence, "risks": item.risks, "evidence_keys": item.evidence_keys, "confidence": item.confidence, "created_at": item.created_at} for item in conclusions]}


@router.post("/topics/{topic_id}/evidence", status_code=201)
def add_evidence(topic_id: UUID, body: ResearchEvidenceCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return research_service.add_evidence(db, _owned(db, user.id, topic_id), body)


@router.post("/topics/{topic_id}/conclusions", status_code=201)
def add_conclusion(topic_id: UUID, body: ResearchConclusionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return research_service.add_conclusion(db, _owned(db, user.id, topic_id), body)


@router.post("/topics/{topic_id}/run", status_code=202)
def run_topic(topic_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    topic = _owned(db, user.id, topic_id)
    research_service.queue_run(db, topic)
    return {"topic_id": str(topic.id), "status": topic.status}


@router.patch("/topics/{topic_id}/monitor", response_model=ResearchTopicResponse)
def update_monitor(topic_id: UUID, body: ResearchMonitorUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return research_service.update_monitor(db, _owned(db, user.id, topic_id), enabled=body.enabled, frequency=body.frequency)
