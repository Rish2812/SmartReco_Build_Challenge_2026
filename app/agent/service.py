import datetime as dt
import logging

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.models import Event, Recommendation, Product
from app.agent.graph import get_recommendation_graph

logger = logging.getLogger("smartreco.agent")


class RecommendationGenerationError(Exception):
    """Raised when the agent graph (Mesh call, retrieval, etc.) fails. The original
    exception is logged in full server-side; this carries a safe summary for the API layer."""
    def __init__(self, message: str, original: Exception):
        super().__init__(message)
        self.original = original


def _summarize_events(db: Session, user_id: int, limit: int = 30) -> str:
    """Turn raw events into a compact text block for the LLM. Kept small on purpose —
    this keeps token usage (and cost) predictable regardless of how active a user is."""
    events = (
        db.query(Event)
        .filter(Event.user_id == user_id)
        .order_by(Event.created_at.desc())
        .limit(limit)
        .all()
    )
    if not events:
        return "No activity recorded yet."

    lines = []
    for e in reversed(events):  # chronological order reads better for the LLM
        if e.event_type == "search":
            lines.append(f"- searched for '{e.query}'")
        elif e.event_type == "view" and e.product_id:
            product = db.query(Product).filter(Product.id == e.product_id).first()
            title = product.title if product else f"product #{e.product_id}"
            lines.append(f"- viewed '{title}'")
        elif e.event_type == "click" and e.product_id:
            product = db.query(Product).filter(Product.id == e.product_id).first()
            title = product.title if product else f"product #{e.product_id}"
            lines.append(f"- clicked on '{title}'")
        elif e.event_type == "time_spent" and e.product_id:
            product = db.query(Product).filter(Product.id == e.product_id).first()
            title = product.title if product else f"product #{e.product_id}"
            duration = (e.metadata_json or {}).get("duration_ms", 0)
            lines.append(f"- spent ~{round(duration / 1000)}s on '{title}'")
        else:
            lines.append(f"- {e.event_type}")
    return "\n".join(lines)


def should_refresh_recommendation(db: Session, user_id: int) -> tuple[bool, str]:
    """
    Production-thinking gate: don't call the LLM on every event.
    Refresh only if enough NEW events have accumulated since the last recommendation,
    AND a minimum cooldown has passed (prevents rapid-fire refresh from bursty clicking).
    """
    total_events = db.query(func.count(Event.id)).filter(Event.user_id == user_id).scalar() or 0
    last_rec = (
        db.query(Recommendation)
        .filter(Recommendation.user_id == user_id)
        .order_by(Recommendation.created_at.desc())
        .first()
    )

    if last_rec is None:
        if total_events == 0:
            return False, "no_activity"
        return True, "first_recommendation"

    new_events = total_events - (last_rec.based_on_event_count or 0)
    if new_events < settings.rec_event_threshold:
        return False, "below_event_threshold"

    seconds_since = (dt.datetime.utcnow() - last_rec.created_at).total_seconds()
    if seconds_since < settings.rec_min_refresh_seconds:
        return False, "cooldown_active"

    return True, "behavior_threshold_crossed"


def generate_and_store_recommendation(db: Session, user_id: int, trigger_reason: str) -> Recommendation:
    events_summary = _summarize_events(db, user_id)
    total_events = db.query(func.count(Event.id)).filter(Event.user_id == user_id).scalar() or 0

    graph = get_recommendation_graph()
    try:
        result = graph.invoke({"user_id": user_id, "events_summary": events_summary})
    except Exception as exc:
        # This is the single place a Mesh call, embedding call, or JSON-parse issue in
        # the agent will surface. Logged loudly and specifically so it's easy to find
        # in `render logs` / the Actions log, rather than a buried generic traceback.
        logger.exception(
            "[RECOMMENDATION AGENT FAILED] user_id=%s mesh_model=%s mesh_base_url=%s error_type=%s",
            user_id, settings.mesh_model, settings.mesh_base_url, type(exc).__name__,
        )
        raise RecommendationGenerationError(f"Agent graph failed: {exc}", exc) from exc

    rec = Recommendation(
        user_id=user_id,
        narrative=result.get("narrative", ""),
        product_ids=result.get("product_ids", []),
        trigger_reason=trigger_reason,
        based_on_event_count=total_events,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def get_or_refresh_recommendation(db: Session, user_id: int) -> Recommendation | None:
    """Cache-first accessor: only calls the (expensive) agent if the trigger gate says so."""
    should_refresh, reason = should_refresh_recommendation(db, user_id)
    if should_refresh:
        return generate_and_store_recommendation(db, user_id, reason)

    return (
        db.query(Recommendation)
        .filter(Recommendation.user_id == user_id)
        .order_by(Recommendation.created_at.desc())
        .first()
    )
