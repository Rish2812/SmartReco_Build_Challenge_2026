from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import User, Product, Event, Recommendation
from app.auth import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
def stats(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return {
        "users": db.query(func.count(User.id)).scalar() or 0,
        "products": db.query(func.count(Product.id)).scalar() or 0,
        "products_vector_synced": db.query(func.count(Product.id)).filter(Product.vector_synced.is_(True)).scalar() or 0,
        "events": db.query(func.count(Event.id)).scalar() or 0,
        "recommendations_generated": db.query(func.count(Recommendation.id)).scalar() or 0,
    }
