"""
Every LLM call in this project goes through this module, which routes to Mesh API
(https://api.meshapi.ai) using the OpenAI-compatible SDK, per the challenge requirement.
"""
from openai import OpenAI

from app.config import settings

_client: OpenAI | None = None


def get_mesh_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=settings.mesh_base_url, api_key=settings.mesh_api_key, timeout=20.0, max_retries=1)
    return _client


def chat_completion(messages: list[dict], model: str | None = None, temperature: float = 0.4) -> str:
    """Single point of entry for chat completions. Returns plain text content."""
    client = get_mesh_client()
    response = client.chat.completions.create(
        model=model or settings.mesh_model,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


def embed_texts(texts: list[str], model: str = "openai/text-embedding-3-small") -> list[list[float]]:
    """Embeddings also routed through Mesh, used for the Chroma vector store."""
    client = get_mesh_client()
    response = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]
