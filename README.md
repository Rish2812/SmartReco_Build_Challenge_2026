# SmartReco — Behavioral AI Recommendation Agent

An agentic recommendation system for an online learning marketplace. It tracks how each
user actually browses, reasons about their interest with an LLM agent, retrieves
matching courses from a real catalog via semantic search, and writes a short persuasive
recommendation — refreshed as behavior evolves, not on every click.

## What's implemented

**Foundation**
- Email/password auth (JWT), two roles: `user` and `admin`. The first registered account
  becomes admin automatically.
- SQLite schema: `users`, `products`, `events`, `recommendations` (see `app/models.py`).

**Dual-write product management**
- Admins add/edit/delete products from `/admin`. Every write goes to SQLite *and* to a
  Chroma vector store (`app/agent/vectorstore.py`) in the same request.
- Each product tracks a `vector_synced` flag so drift between the two stores is visible
  in the admin panel rather than silently hidden.

**Behavioral event tracking**
- `app/static/js/tracker.js` batches events client-side (flushes every 8s or every 10
  events, whichever comes first), throttles high-frequency `time_spent` pings to once per
  5s, and flushes via `fetch(..., {keepalive: true})` so it survives page navigation
  without blocking the UI thread.
- Server side, `/events/batch` does a single bulk insert per batch instead of one write
  per event.

**Agentic recommendation engine (LangGraph)**
- `app/agent/graph.py` wires four nodes: `analyze_activity → retrieve → grade_retrieval
  → generate_copy`, with a conditional edge that loops back to `retrieve` (broadening the
  query, dropping the category filter) up to twice if retrieval quality looks weak, before
  generating anyway with whatever was found.
- Retrieval is grounded in the real catalog — the copy-generation prompt is only given
  candidate products actually returned by the vector search, and is instructed not to
  invent products.
- All LLM/embedding calls route through **Mesh API** via the OpenAI SDK
  (`app/agent/mesh_client.py`) — this is the single choke point, per the challenge
  requirement.

**Efficiency / production thinking**
- `app/agent/service.py` gates every recommendation refresh: it only calls the agent if
  (a) enough new events have accumulated since the last recommendation
  (`REC_EVENT_THRESHOLD`, default 5), and (b) a minimum cooldown has passed since the last
  refresh (`REC_MIN_REFRESH_SECONDS`, default 120s). Otherwise it serves the cached
  `Recommendation` row. This is what stops a burst of clicks from firing an LLM call per
  click.

**Bonus features implemented**
- ⭐ **Structured agent framework** — LangGraph, as above (analyze → retrieve → grade →
  generate, with a retry edge).
- ⭐ **Scheduled proactive delivery** — `app/scheduler/digest.py` runs a real
  `APScheduler` cron job (`DIGEST_SEND_HOUR`/`DIGEST_SEND_MINUTE` in `.env`) that
  re-checks each user through the same cache-first gate and emails a digest (or logs it,
  if SMTP isn't configured, so the mechanism is still demonstrable without real mail
  credentials).
- ⭐ **Retrieval polish** — metadata filtering by inferred category, plus a quality gate
  (`grade_retrieval`) that broadens and retries when results look weak.

**Not implemented:** LangSmith observability tracing (out of scope for this pass —
`chat_completion`/`semantic_search` are centralized enough to add tracing later without
touching call sites).

## Architecture

```
Browser (Jinja2 + tracker.js)
   │  batched events
   ▼
FastAPI (app/main.py, app/routers/*)
   │                              │
   ▼                              ▼
SQLite (users, products,     Chroma vector store
events, recommendations)     (product embeddings)
   │                              │
   └──────────┬───────────────────┘
              ▼
   LangGraph agent (app/agent/graph.py)
   analyze → retrieve → grade → generate
              │
              ▼
        Mesh API (chat + embeddings)

APScheduler (app/scheduler/digest.py) — daily cron, reuses the same
cache-first recommendation gate, emails or logs a digest per user.
```

## Catalog data

`scripts/seed_products.py` seeds ~396 courses: 14 hand-written (Agentic AI / QA
Automation focus) plus 382 curated from two public Kaggle datasets — Udemy course
metadata and Coursera course metadata (`scripts/data/`). `scripts/curate_external_courses.py`
documents exactly how those 382 were selected (top courses by popularity/rating per
category, deduplicated, capped per category to keep vector-store embedding time
reasonable) and classified into categories (keyword rules for Coursera, since that
dataset has no category field). Re-running it regenerates `scripts/_external_catalog_data.py`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set MESH_API_KEY=rsk_...  (get one from the Mesh dashboard)

python -m scripts.seed_products  # optional: seeds ~14 demo courses + demo accounts
uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000`.

Demo accounts (created by the seed script):
- Admin: `admin@smartreco.local` / `admin123`
- User: `user@smartreco.local` / `user1234`

Or just register your own account from `/login` — the first account created becomes
admin automatically.

## Trying it out

1. Log in as the demo user, browse a handful of courses in one category (e.g. click into
   a couple of "Agentic AI" courses, search "langgraph").
2. Visit `/dashboard` — once ≥5 events have been tracked, a recommendation generates.
   Browse more and refresh `/dashboard` again to see it update.
3. Log in as admin (`/admin`) to add/edit/delete products and watch the `vector_synced`
   column, and to see aggregate stats.

## Project layout

```
app/
  main.py                 FastAPI app, page routes, startup/scheduler wiring
  config.py, database.py, models.py, schemas.py, auth.py
  routers/                auth, products, events, recommendations, admin
  agent/
    mesh_client.py         single choke point for all LLM/embedding calls (via Mesh)
    vectorstore.py         Chroma dual-write + semantic_search
    nodes.py, graph.py      LangGraph node functions + graph wiring
    service.py              trigger/caching logic, event summarization
  scheduler/digest.py       APScheduler daily digest job
  templates/, static/       Jinja2 pages, tracker.js, style.css
scripts/
  seed_products.py          demo catalog + accounts
  smoke_test.py              in-process end-to-end smoke test (FastAPI TestClient)
```

## Notes on the CI checks

`.github/workflows/smartreco-checks.yml` is the workflow provided by the challenge. Add
`MESH_API_KEY` and `SUBMISSION_TOKEN` as repository secrets (Settings → Secrets and
variables → Actions) for it to run.
