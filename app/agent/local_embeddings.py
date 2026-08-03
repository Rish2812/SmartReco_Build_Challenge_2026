"""
Mesh's free tier (as of this build) offers only text-generation models — no embedding
model is available for free (see README for the exact free-tier list we checked against).

Rather than block RAG retrieval on a paid embedding call, we compute embeddings locally
using the classic "hashing trick" (feature hashing, à la Vowpal Wabbit / sklearn's
HashingVectorizer): each token is hashed into one of `dim` buckets with a signed
contribution, then the vector is L2-normalized. This is stateless (no corpus fitting
required, unlike TF-IDF), needs zero external calls or heavy ML runtimes, and is good
enough to support keyword/topic-driven retrieval over a course catalog.

This is a deliberate, documented trade-off — swap `embed_texts_local` back for
`app.agent.mesh_client.embed_texts` in vectorstore.py in one line if/when a free (or
budgeted) embedding model becomes available on Mesh.
"""
import hashlib
import math
import re

TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _hash_bucket(token: str, dim: int) -> tuple[int, int]:
    digest = hashlib.md5(token.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % dim
    sign = 1 if digest[4] % 2 == 0 else -1
    return index, sign


def embed_text_local(text: str, dim: int = 384) -> list[float]:
    vec = [0.0] * dim
    for token in _tokenize(text):
        idx, sign = _hash_bucket(token, dim)
        vec[idx] += sign

    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed_texts_local(texts: list[str], dim: int = 384) -> list[list[float]]:
    return [embed_text_local(t, dim) for t in texts]
