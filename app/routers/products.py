from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product, User
from app.schemas import ProductCreate, ProductUpdate, ProductOut
from app.auth import require_admin
from app.agent.vectorstore import upsert_product, delete_product as vs_delete_product

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
def list_products(category: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Product).filter(Product.is_active.is_(True))
    if category:
        q = q.filter(Product.category == category)
    return q.order_by(Product.created_at.desc()).all()


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("", response_model=ProductOut)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)

    # Dual-write: sync into the vector store right after the SQL write.
    synced = upsert_product(product.id, product.title, product.description, product.category, product.level, product.price)
    product.vector_synced = synced
    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)

    # Keep vector store in sync with any content-affecting change.
    synced = upsert_product(product.id, product.title, product.description, product.category, product.level, product.price)
    product.vector_synced = synced
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    db.delete(product)
    db.commit()
    vs_delete_product(product_id)  # keep vector store in sync
    return {"ok": True}
