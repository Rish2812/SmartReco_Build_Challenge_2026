from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Product
from app.schemas import RecommendationOut, ProductOut
from app.auth import get_current_user
from app.agent.service import get_or_refresh_recommendation

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/me", response_model=RecommendationOut)
def my_recommendation(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rec = get_or_refresh_recommendation(db, user.id)
    if not rec:
        raise HTTPException(status_code=404, detail="No recommendation yet — browse a bit first")

    products = db.query(Product).filter(Product.id.in_(rec.product_ids or [])).all()
    # preserve the agent's ranking order
    order = {pid: i for i, pid in enumerate(rec.product_ids or [])}
    products.sort(key=lambda p: order.get(p.id, 999))

    return RecommendationOut(
        id=rec.id,
        narrative=rec.narrative,
        products=[ProductOut.model_validate(p) for p in products],
        trigger_reason=rec.trigger_reason,
        created_at=rec.created_at,
    )
