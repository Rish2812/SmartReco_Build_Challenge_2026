"""
One-time curation pass over the raw Udemy + Coursera datasets, producing a Python
literal (printed to stdout) that gets pasted into scripts/seed_products.py's CATALOG.

We curate rather than dump wholesale because:
- The Udemy dataset's 4 subjects (Web Dev, Business Finance, Graphic Design, Musical
  Instruments) aren't all relevant to a professional learning platform in equal measure.
- Coursera's data has no category field at all -- titles need keyword classification.
- Every product gets locally embedded on every app startup (see app/main.py
  resync_vector_store) -- thousands of rows would make every deploy slow for no benefit.
"""
import csv
import re
import random

random.seed(42)

UDEMY_LEVEL_MAP = {
    "All Levels": "beginner",
    "Beginner Level": "beginner",
    "Intermediate Level": "intermediate",
    "Expert Level": "advanced",
}
COURSERA_LEVEL_MAP = {
    "Beginner": "beginner",
    "Mixed": "intermediate",
    "Intermediate": "intermediate",
    "Advanced": "advanced",
}

# Udemy subjects worth including, and how many top-by-popularity to keep from each.
UDEMY_SUBJECT_CAPS = {
    "Web Development": 70,
    "Business Finance": 55,
    "Graphic Design": 35,
    "Musical Instruments": 20,
}

# Ordered keyword -> category rules for classifying Coursera titles (first match wins).
COURSERA_RULES = [
    ("Cybersecurity", ["security", "cybersecurity", "ethical hacking", "sscp", "cissp", "network defense"]),
    ("Agentic AI", ["machine learning", "deep learning", "neural network", "artificial intelligence",
                     "ai for", "reinforcement learning", "natural language processing", " nlp ",
                     "generative ai", "computer vision", "ai foundations"]),
    ("Backend Development", ["aws", "cloud", "devops", "kubernetes", "docker", "system design",
                               "software engineering", "backend", " api "]),
    ("Data Science", ["data science", "data analysis", "analytics", "statistics", "sql",
                        "excel", "tableau", "r programming", "big data", "data visualization"]),
    ("Web Development", ["web development", "javascript", "html", "css", "react", "front-end", "frontend"]),
    ("Business Finance", ["finance", "financial", "accounting", "marketing", "business strategy",
                             "entrepreneurship", "economics", "investment", "management"]),
    ("Career Growth", ["leadership", "communication skills", "career", "negotiation", "productivity",
                          "public speaking", "resume", "interview skills", "project management"]),
]
COURSERA_CAP_PER_CATEGORY = 45


def parse_students(raw: str) -> float:
    raw = raw.strip().lower()
    mult = 1
    if raw.endswith("k"):
        mult, raw = 1_000, raw[:-1]
    elif raw.endswith("m"):
        mult, raw = 1_000_000, raw[:-1]
    try:
        return float(raw) * mult
    except ValueError:
        return 0.0


def clean_title(t: str) -> str:
    return " ".join(t.strip().split())


def is_english_title(title: str) -> bool:
    """Filters out localized/translated catalog entries (Cyrillic, CJK, Arabic, etc.).
    Both source datasets include non-English versions of some courses under the same
    subject; this platform's UI/copy is English-only, so mixed-script titles look broken."""
    letters = re.findall(r"[^\W\d_]", title, re.UNICODE)
    if not letters:
        return True
    latin_count = sum(1 for ch in letters if re.match(r"[A-Za-z\u00C0-\u024F]", ch))
    return (latin_count / len(letters)) > 0.85


def curate_udemy():
    import os
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "Udemy_Courses.csv")
    rows_by_subject = {}
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            subj = row["subject"]
            if subj not in UDEMY_SUBJECT_CAPS:
                continue
            try:
                subs = int(row["num_subscribers"])
            except ValueError:
                subs = 0
            rows_by_subject.setdefault(subj, []).append((subs, row))

    out = []
    seen_titles = set()
    for subj, cap in UDEMY_SUBJECT_CAPS.items():
        candidates = sorted(rows_by_subject.get(subj, []), key=lambda x: -x[0])
        picked = 0
        for subs, row in candidates:
            if picked >= cap:
                break
            title = clean_title(row["course_title"])
            key = title.lower()
            if key in seen_titles or len(title) > 90 or not is_english_title(title):
                continue
            seen_titles.add(key)
            level = UDEMY_LEVEL_MAP.get(row["level"], "beginner")
            is_paid = row["is_paid"].strip().upper() == "TRUE"
            try:
                price = float(row["price"]) if is_paid else 0.0
            except ValueError:
                price = 0.0
            duration = row["content_duration"].strip()
            lectures = row["num_lectures"].strip()
            desc = f"{lectures} lectures, {duration} of content. {subs:,} students enrolled on the original platform."
            out.append((title, desc, subj, round(price), level))
            picked += 1
    return out


def classify_coursera(title: str):
    t = f" {title.lower()} "
    for category, keywords in COURSERA_RULES:
        for kw in keywords:
            if kw in t:
                return category
    return None


def curate_coursera():
    import os
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "coursea_data.csv")
    rows_by_category = {}
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            title = clean_title(row["course_title"])
            category = classify_coursera(title)
            if not category:
                continue
            try:
                rating = float(row["course_rating"])
            except ValueError:
                rating = 0.0
            students = parse_students(row["course_students_enrolled"])
            score = rating * (students ** 0.15)  # favor high rating, mild popularity boost
            rows_by_category.setdefault(category, []).append((score, row, students))

    out = []
    seen_titles = set()
    for category, candidates in rows_by_category.items():
        candidates.sort(key=lambda x: -x[0])
        picked = 0
        for score, row, students in candidates:
            if picked >= COURSERA_CAP_PER_CATEGORY:
                break
            title = clean_title(row["course_title"])
            key = title.lower()
            if key in seen_titles or len(title) > 90 or not is_english_title(title):
                continue
            seen_titles.add(key)
            level = COURSERA_LEVEL_MAP.get(row["course_difficulty"], "beginner")
            org = row["course_organization"].strip()
            cert = row["course_Certificate_type"].strip()
            rating = row["course_rating"].strip()
            students_display = row["course_students_enrolled"].strip()
            desc = f"{cert.title()} from {org}. Rated {rating}/5 by {students_display} learners on the original platform."
            # Coursera courses are typically subscription/audit based; treat as accessible-priced.
            price = random.choice([0, 0, 29, 49, 59])
            out.append((title, desc, category, price, level))
            picked += 1
    return out


if __name__ == "__main__":
    udemy = curate_udemy()
    coursera = curate_coursera()
    all_courses = udemy + coursera

    from collections import Counter
    cat_counts = Counter(c[2] for c in all_courses)
    print(f"# Curated {len(all_courses)} courses total")
    print(f"# By category: {dict(cat_counts)}")
    print()
    print("EXTERNAL_CATALOG = [")
    for title, desc, category, price, level in all_courses:
        title_e = title.replace('"', "'")
        desc_e = desc.replace('"', "'")
        print(f'    ("{title_e}", "{desc_e}", "{category}", {price}, "{level}"),')
    print("]")
