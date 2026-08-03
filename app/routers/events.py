from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event, User
from app.schemas import EventBatch
from app.auth import get_current_user

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/batch")
def ingest_events(payload: EventBatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Accepts a batch of events from the frontend tracker in one call. The tracker is
    responsible for batching/throttling client-side (see static/js/tracker.js); this
    endpoint just does a single bulk insert so the request stays cheap server-side too.
    """
    rows = [
        Event(
            user_id=user.id,
            event_type=e.event_type,
            product_id=e.product_id,
            query=e.query,
            metadata_json=e.metadata,
        )
        for e in payload.events
    ]
    db.bulk_save_objects(rows)
    db.commit()
    return {"ingested": len(rows)}
