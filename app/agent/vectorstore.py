"""
Vector store for semantic product retrieval (RAG). Products are dual-written here
whenever they're created/updated/deleted in SQL, via app/routers/products.py.
"""
import chromadb

from app.config import settings
from app.agent.mesh_client import embed_texts

_client = None
_collection = None

COLLECTION_NAME = "smartreco_products"


def get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        _collection = _client.get_or_create_collection(name=COLLECTION_NAME)
    return _collection


def _product_document(title: str, description: str, category: str, level: str) -> str:
    return f"{title}\nCategory: {category}\nLevel: {level}\n{description}"


def upsert_product(product_id: int, title: str, description: str, category: str, level: str, price: float) -> bool:
    """Write/update a product's embedding in Chroma. Returns True on success (used to
    flag `vector_synced` on the SQL row so dual-write drift is observable)."""
    try:
        collection = get_collection()
        doc = _product_document(title, description, category, level)
        [embedding] = embed_texts([doc])
        collection.upsert(
            ids=[str(product_id)],
            embeddings=[embedding],
            documents=[doc],
            metadatas=[{"category": category, "level": level, "price": price, "title": title}],
        )
        return True
    except Exception:
        return False


def delete_product(product_id: int) -> None:
    try:
        collection = get_collection()
        collection.delete(ids=[str(product_id)])
    except Exception:
        pass


def semantic_search(query_text: str, n_results: int = 8, category_filter: str | None = None) -> list[dict]:
    """Retrieve candidate products by semantic similarity, grounded in the real catalog."""
    collection = get_collection()
    [embedding] = embed_texts([query_text])
    where = {"category": category_filter} if category_filter else None
    results = collection.query(query_embeddings=[embedding], n_results=n_results, where=where)

    hits = []
    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    for pid, dist, meta in zip(ids, distances, metadatas):
        hits.append({"product_id": int(pid), "distance": dist, "metadata": meta})
    return hits
