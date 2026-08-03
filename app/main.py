from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Product
from app.routers import auth, products, events, recommendations, admin
from app.scheduler.digest import start_scheduler

Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
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
