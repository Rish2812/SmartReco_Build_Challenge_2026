import json
from typing import TypedDict, Optional

from app.agent.mesh_client import chat_completion
from app.agent.vectorstore import semantic_search


class AgentState(TypedDict, total=False):
    user_id: int
    events_summary: str          # compact text summary of recent behavior fed to the LLM
    retrieval_query: str         # query derived from behavior, used for semantic search
    category_hint: Optional[str]
    retrieved: list[dict]        # candidate products from Chroma
    retrieval_ok: bool
    retry_count: int
    narrative: str
    product_ids: list[int]


MAX_RETRIEVAL_RETRIES = 2


def analyze_activity(state: AgentState) -> AgentState:
    """Reason over the user's raw behavioral events and turn them into a retrieval query."""
    prompt = f"""You are analyzing a user's browsing behavior on an online learning marketplace.

Recent activity:
{state['events_summary']}

Based on this, respond with ONLY a JSON object (no markdown fences, no prose) with these keys:
- "interest_summary": one sentence describing what this user seems interested in right now
- "search_query": a short search-engine-style query (5-12 words) capturing that interest, to retrieve matching courses
- "category_hint": your best guess at a single course category name that matches, or null if unclear
"""
    raw = chat_completion([{"role": "user", "content": prompt}], temperature=0.2)
    try:
        parsed = json.loads(raw.strip().strip("`").removeprefix("json").strip())
    except (json.JSONDecodeError, AttributeError):
        parsed = {"interest_summary": state["events_summary"][:200], "search_query": state["events_summary"][:100], "category_hint": None}

    state["retrieval_query"] = parsed.get("search_query") or state["events_summary"][:100]
    state["category_hint"] = parsed.get("category_hint")
    state["_interest_summary"] = parsed.get("interest_summary", "")
    state["retry_count"] = 0
    return state


def retrieve(state: AgentState) -> AgentState:
    """Semantic retrieval over the real product catalog via the vector store."""
    hits = semantic_search(
        query_text=state["retrieval_query"],
        n_results=8,
        category_filter=state.get("category_hint"),
    )
    state["retrieved"] = hits
    return state


def grade_retrieval(state: AgentState) -> AgentState:
    """Decide whether retrieval quality is good enough, or whether to broaden and retry."""
    hits = state.get("retrieved", [])
    good = len(hits) >= 3 and any(h["distance"] < 0.8 for h in hits)
    state["retrieval_ok"] = good
    if not good and state.get("retry_count", 0) < MAX_RETRIEVAL_RETRIES:
        # Broaden: drop the category filter and retry with a shorter, looser query.
        state["category_hint"] = None
        state["retrieval_query"] = " ".join(state["retrieval_query"].split()[:5])
        state["retry_count"] = state.get("retry_count", 0) + 1
    return state


def should_retry(state: AgentState) -> str:
    if state.get("retrieval_ok"):
        return "generate"
    if state.get("retry_count", 0) < MAX_RETRIEVAL_RETRIES:
        return "retrieve"
    return "generate"  # give up gracefully and generate with whatever we have


def generate_copy(state: AgentState) -> AgentState:
    """Generate the persuasive, personalized recommendation narrative grounded in retrieved products."""
    hits = state.get("retrieved", [])[:4]
    if not hits:
        state["narrative"] = (
            "We're still learning what you're into — browse a few more courses and "
            "we'll have tailored picks ready for you."
        )
        state["product_ids"] = []
        return state

    catalog_snippet = "\n".join(
        f"- id={h['product_id']}: {h['metadata'].get('title')} "
        f"(category: {h['metadata'].get('category')}, level: {h['metadata'].get('level')}, "
        f"price: {h['metadata'].get('price')})"
        for h in hits
    )

    prompt = f"""You are a persuasive but honest recommendation copywriter for an online learning marketplace.

User's inferred interest: {state.get('_interest_summary', '')}
Recent activity summary: {state['events_summary']}

Candidate courses actually in the catalog (ONLY recommend from this list, do not invent courses):
{catalog_snippet}

Write a short, warm, persuasive recommendation (3-5 sentences) that:
- References what the user has specifically been doing/searching for
- Builds a light narrative about why now is a good time to act
- Naturally leads into the recommended courses (do not just list them mechanically)
- Avoids generic hype; be specific and genuine

Then on a new line, output exactly: RECOMMENDED_IDS: <comma-separated product ids from the candidates above, best 2-3 picks>
"""
    raw = chat_completion([{"role": "user", "content": prompt}], temperature=0.6)

    narrative = raw
    product_ids: list[int] = []
    if "RECOMMENDED_IDS:" in raw:
        narrative, ids_part = raw.split("RECOMMENDED_IDS:", 1)
        narrative = narrative.strip()
        for tok in ids_part.strip().split(","):
            tok = tok.strip()
            if tok.isdigit():
                product_ids.append(int(tok))

    if not product_ids:
        product_ids = [h["product_id"] for h in hits[:3]]

    state["narrative"] = narrative.strip()
    state["product_ids"] = product_ids
    return state
