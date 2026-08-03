"""
Seeds a demo catalog. Run with:  python -m scripts.seed_products

Creates courses across a few categories so retrieval has something meaningful to
differentiate between, plus a demo admin and demo user account.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, engine, SessionLocal
from app.models import Product, User
from app.auth import hash_password
from app.agent.vectorstore import upsert_product

Base.metadata.create_all(bind=engine)

CATALOG = [
    # Agentic AI / LLM
    ("Agentic AI Systems with LangGraph", "Design multi-step reasoning agents with LangGraph: state machines, tool use, retries, and human-in-the-loop patterns for production agents.", "Agentic AI", 149, "advanced"),
    ("Retrieval-Augmented Generation in Practice", "Build RAG pipelines: chunking strategies, embeddings, vector databases, re-ranking, and grounding LLM answers in real data.", "Agentic AI", 129, "intermediate"),
    ("Intro to LLM Application Development", "Get hands-on with prompting, function calling, and building your first LLM-powered app from scratch.", "Agentic AI", 79, "beginner"),
    ("Multi-Agent Orchestration: CrewAI & AutoGen", "Coordinate teams of specialized agents to tackle complex workflows, with real orchestration patterns and failure handling.", "Agentic AI", 159, "advanced"),

    # QA / Test Automation
    ("Playwright Test Automation Masterclass", "End-to-end testing with Playwright: fixtures, parallelization, CI integration, and flaky-test debugging.", "QA Automation", 99, "intermediate"),
    ("CI/CD for QA Engineers", "Wire test suites into GitHub Actions and Jenkins pipelines, with reporting, gating, and rollback strategies.", "QA Automation", 89, "intermediate"),
    ("Foundations of Software Testing", "Test design fundamentals: equivalence classes, boundary analysis, and writing tests that actually catch bugs.", "QA Automation", 59, "beginner"),

    # Data Science
    ("Practical Data Science with Python", "Pandas, visualization, and statistical thinking for real datasets — from messy CSV to clean insight.", "Data Science", 99, "beginner"),
    ("Deep Learning for Computer Vision", "CNNs, transfer learning, and object detection, building toward a real image-classification project.", "Data Science", 179, "advanced"),
    ("Vector Databases & Semantic Search", "How embeddings work, and how to build fast, accurate semantic search over large document sets.", "Data Science", 119, "intermediate"),

    # Career & Immigration-adjacent (general professional skills)
    ("Technical Portfolio & LinkedIn Positioning", "Position your technical profile for visibility: portfolio structure, LinkedIn headlines, and search optimization.", "Career Growth", 49, "beginner"),
    ("Personal Finance for Tech Professionals", "Budgeting, tax-advantaged accounts, and long-term saving strategies tailored for salaried tech workers.", "Career Growth", 39, "beginner"),

    # Backend Dev
    ("FastAPI for Production", "Build robust, well-tested APIs with FastAPI: dependency injection, background tasks, auth, and deployment.", "Backend Development", 109, "intermediate"),
    ("System Design for Backend Engineers", "Scalability patterns, caching, queues, and database design trade-offs through real interview-style problems.", "Backend Development", 139, "advanced"),
]


def run():
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "admin@smartreco.local").first():
            db.add(User(email="admin@smartreco.local", hashed_password=hash_password("admin123"), role="admin"))
        if not db.query(User).filter(User.email == "user@smartreco.local").first():
            db.add(User(email="user@smartreco.local", hashed_password=hash_password("user1234"), role="user"))
        db.commit()

        created = 0
        for title, description, category, price, level in CATALOG:
            if db.query(Product).filter(Product.title == title).first():
                continue
            product = Product(title=title, description=description, category=category, price=price, level=level)
            db.add(product)
            db.commit()
            db.refresh(product)
            synced = upsert_product(product.id, title, description, category, level, price)
            product.vector_synced = synced
            db.commit()
            created += 1

        print(f"Seeded {created} new products.")
        print("Demo admin login: admin@smartreco.local / admin123")
        print("Demo user login:  user@smartreco.local / user1234")
    finally:
        db.close()


if __name__ == "__main__":
    run()
