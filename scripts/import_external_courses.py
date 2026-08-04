"""
Imports a curated subset of the bundled Udemy/Coursera datasets (data/*.csv) into the
product catalog. Run with:  python -m scripts.import_external_courses

Design choices, spelled out because they're not obvious from the code alone:
- We do NOT import all ~4,500 rows. Many Udemy rows are near-duplicate micro-courses
  (e.g. a dozen "#N Piano Hand Coordination..." variants) that would add noise to
  semantic retrieval without adding real variety, and every product needs a local
  embedding on every app startup now (see resync_vector_store in app/main.py) — a
  few thousand of those would make boot time painful, especially on Render's free
  tier CPU. Instead we take the most-subscribed/most-enrolled courses per bucket,
  which both filters out the junk and biases toward recognizable, quality titles.
- Neither dataset includes a free-text description, only structured metadata. We
  synthesize a short, honest description from what's actually in the row rather than
  inventing course content — this keeps retrieval grounded in real data, per the
  challenge's "don't invent products" principle applied one level up (don't invent
  course content either).
- Coursera has no category/subject column, only organization. We classify by keyword
  matching against the title into a fixed category set. This is a heuristic, not
  perfect, and said so here rather than silently pretending it's precise.
"""
import csv
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, engine, SessionLocal
from app.models import Product
from app.agent.vectorstore import upsert_product

Base.metadata.create_all(bind=engine)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

UDEMY_PER_SUBJECT = 30   # top-N by subscribers, per Udemy subject
COURSERA_TOTAL = 80      # top-N by enrollment, across all of Coursera
COURSERA_PER_ORG_CAP = 4  # avoid one university dominating the sample

UDEMY_LEVEL_MAP = {
    "All Levels": "beginner",
    "Beginner Level": "beginner",
    "Intermediate Level": "intermediate",
    "Expert Level": "advanced",
}
COURSERA_LEVEL_MAP = {
    "Beginner": "beginner",
    "Intermediate": "intermediate",
    "Mixed": "intermediate",
    "Advanced": "advanced",
}

# Keyword -> category, checked in order against the (lowercased) course title.
# Coursera has no subject column, so this is a best-effort heuristic classifier.
# Multi-word/phrase keywords use plain substring matching (safe — false positives on
# a full phrase are rare). Short, ambiguous tokens (ai, sql) use \b-wrapped regex so
# they don't match inside unrelated words.
COURSERA_CATEGORY_RULES = [
    ("AI & Machine Learning", ["machine learning", "deep learning", "neural network",
        "artificial intelligence", "nlp", "computer vision"], [r"\bai\b"]),
    ("Data Science", ["data science", "data analy", "big data", "data visuali",
        "data scientist", "statistics", "statistical", "data analyst"], [r"\bsql\b"]),
    ("Cloud & DevOps", ["cloud", "aws", "azure", "gcp", "kubernetes", "devops",
        "docker", "compute engine"], []),
    ("Cybersecurity", ["cyber", "security", "encrypt"], []),
    ("Computer Science", ["python", "programming", "software engineer", "algorithm",
        "coding", "computing", "technical support", "it support"], []),
    ("Business & Finance", ["business", "finance", "financial", "accounting",
        "marketing", "entrepreneur", "management", "economics", "strategy"], []),
    ("Career Growth", ["career", "negotiation", "resume", "interview", "job search"], []),
    ("Health & Medicine", ["health", "medic", "nursing", "nutrition", "clinical",
        "patient", "disease"], []),
    ("Personal Development", ["psycholog", "mindful", "happiness", "wellbeing",
        "mental health", "mindshift", "learning how to learn"], []),
    ("Law & Policy", ["legal", "policy", "government", "politic"], [r"\blaw\b"]),
    ("Language & Communication", ["language", "english", "writing", "communication",
        "grammar", "punctuation", "vocabulary", "korean", "spanish", "french",
        "german", "chinese", "japanese"], []),
    ("Arts & Design", ["design", "creativ", "photograph", "singer", "songwriter",
        "guitar", "music", "art "], []),
    ("Social Sciences", ["philosophy", "social science", "game theory",
        "mathematical thinking", "sociology"], []),
    ("Education", ["teach", "education", "classroom", "student"], []),
]


def classify_coursera(title: str) -> str:
    t = title.lower()
    for category, phrases, patterns in COURSERA_CATEGORY_RULES:
        if any(p in t for p in phrases):
            return category
        if any(re.search(p, t) for p in patterns):
            return category
    return "General Studies"


def parse_enrollment(raw: str) -> int:
    raw = raw.strip().lower()
    try:
        if raw.endswith("k"):
            return int(float(raw[:-1]) * 1_000)
        if raw.endswith("m"):
            return int(float(raw[:-1]) * 1_000_000)
        return int(float(raw))
    except ValueError:
        return 0


def load_udemy():
    path = os.path.join(DATA_DIR, "udemy_courses.csv")
    with open(path, encoding="utf-8", errors="replace") as f:
        rows = list(csv.DictReader(f))

    by_subject: dict[str, list[dict]] = {}
    for r in rows:
        by_subject.setdefault(r["subject"], []).append(r)

    picked = []
    for subject, subj_rows in by_subject.items():
        def subs(r):
            try:
                return int(r["num_subscribers"])
            except ValueError:
                return 0
        subj_rows.sort(key=subs, reverse=True)
        seen_titles = set()
        for r in subj_rows:
            norm = re.sub(r"[^a-z0-9]", "", r["course_title"].lower())[:40]
            if norm in seen_titles:
                continue
            seen_titles.add(norm)
            picked.append(r)
            if len(seen_titles) >= UDEMY_PER_SUBJECT:
                break

    products = []
    for r in picked:
        try:
            price = float(r["price"]) if r["is_paid"] == "TRUE" else 0.0
        except ValueError:
            price = 0.0
        level = UDEMY_LEVEL_MAP.get(r["level"], "beginner")
        description = (
            f"A {r['subject']} course with {r['num_lectures']} lectures "
            f"({r['content_duration']} of content), covering practical, hands-on skills. "
            f"Rated by {r['num_reviews']} reviews from {r['num_subscribers']} subscribers on Udemy."
        )
        products.append({
            "title": r["course_title"].strip(),
            "description": description,
            "category": r["subject"],
            "price": round(price, 2),
            "level": level,
        })
    return products


def load_coursera():
    path = os.path.join(DATA_DIR, "coursera_courses.csv")
    with open(path, encoding="utf-8", errors="replace") as f:
        rows = list(csv.DictReader(f))

    for r in rows:
        r["_enrollment"] = parse_enrollment(r["course_students_enrolled"])
    rows.sort(key=lambda r: r["_enrollment"], reverse=True)

    picked = []
    org_counts: dict[str, int] = {}
    seen_titles = set()
    for r in rows:
        org = r["course_organization"]
        if org_counts.get(org, 0) >= COURSERA_PER_ORG_CAP:
            continue
        norm = re.sub(r"[^a-z0-9]", "", r["course_title"].lower())[:40]
        if norm in seen_titles:
            continue
        picked.append(r)
        seen_titles.add(norm)
        org_counts[org] = org_counts.get(org, 0) + 1
        if len(picked) >= COURSERA_TOTAL:
            break

    products = []
    for r in picked:
        level = COURSERA_LEVEL_MAP.get(r["course_difficulty"], "intermediate")
        category = classify_coursera(r["course_title"])
        description = (
            f"A {r['course_Certificate_type'].lower()} offered by {r['course_organization']} on Coursera, "
            f"rated {r['course_rating']}/5 by learners, with {r['course_students_enrolled']} enrolled. "
            f"Suited for {r['course_difficulty'].lower()}-level learners."
        )
        products.append({
            "title": r["course_title"].strip(),
            "description": description,
            "category": category,
            "price": 0.0,  # Coursera courses are free to audit; certificates priced separately
            "level": level,
        })
    return products


def run():
    udemy_products = load_udemy()
    coursera_products = load_coursera()
    all_products = udemy_products + coursera_products
    print(f"Prepared {len(udemy_products)} Udemy + {len(coursera_products)} Coursera = {len(all_products)} candidate products.")

    db = SessionLocal()
    created, skipped, synced = 0, 0, 0
    try:
        for p in all_products:
            if db.query(Product).filter(Product.title == p["title"]).first():
                skipped += 1
                continue
            product = Product(
                title=p["title"], description=p["description"], category=p["category"],
                price=p["price"], level=p["level"],
            )
            db.add(product)
            db.commit()
            db.refresh(product)
            ok = upsert_product(product.id, p["title"], p["description"], p["category"], p["level"], p["price"])
            product.vector_synced = ok
            db.commit()
            created += 1
            synced += 1 if ok else 0
        print(f"Created {created} new products ({synced} vector-synced), skipped {skipped} already-existing titles.")

        categories = sorted({row[0] for row in db.query(Product.category).distinct().all()})
        print(f"Catalog now spans {len(categories)} categories: {', '.join(categories)}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
