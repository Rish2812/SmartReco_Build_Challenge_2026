from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db, SessionLocal
from app.models import Product
from app.routers import auth, products, events, recommendations, admin
from app.scheduler.digest import start_scheduler
from app.agent.vectorstore import upsert_product

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("smartreco.startup")

Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="app/templates")


def resync_vector_store() -> None:
    """
    Postgres now persists across deploys, but Chroma's disk is still ephemeral on
    Render's free tier — every fresh container starts with an empty vector store even
    though the product catalog in Postgres is untouched. Without this, retrieval would
    silently return zero hits after every redeploy until an admin manually re-saved
    each product. Runs on every startup; cheap since embeddings are local (no Mesh call).
    """
    db = SessionLocal()
    try:
        all_products = db.query(Product).all()
        synced = 0
        for p in all_products:
            ok = upsert_product(p.id, p.title, p.description, p.category, p.level, p.price)
            if ok and not p.vector_synced:
                p.vector_synced = True
        db.commit()
        for p in all_products:
            synced += 1 if p.vector_synced else 0
        logger.info("Vector store resync complete: %s/%s products synced.", synced, len(all_products))
    except Exception:
        logger.exception("Vector store resync failed on startup.")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    resync_vector_store()
    scheduler = start_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="SmartReco", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(events.router)
app.include_router(recommendations.router)
app.include_router(admin.router)


@app.get("/")
def home(request: Request, category: str | None = None, q: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Product).filter(Product.is_active.is_(True))
    if category:
        query = query.filter(Product.category == category)
    if q:
        like = f"%{q}%"
        query = query.filter((Product.title.ilike(like)) | (Product.description.ilike(like)))
    products_list = query.order_by(Product.created_at.desc()).all()
    categories = sorted({p.category for p in db.query(Product).filter(Product.is_active.is_(True)).all()})
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "products": products_list, "categories": categories, "active_category": category, "search_query": q},
    )


@app.get("/product/{product_id}")
def product_detail(product_id: int, request: Request, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return templates.TemplateResponse("404.html", {"request": request, "reason": "That course doesn't exist (or was removed)."}, status_code=404)
    return templates.TemplateResponse("product.html", {"request": request, "product": product})


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard")
def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/admin")
def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return templates.TemplateResponse("404.html", {"request": request, "reason": "Page not found."}, status_code=404)
