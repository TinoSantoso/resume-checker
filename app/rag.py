"""Build & query the RAG knowledge base (ChromaDB + Ollama nomic-embed-text).

Multi-role KB
-------------
Starting with v0.4 (task #5), the KB holds rules from ALL rubrics in a
single collection. Each rule document carries a ``role`` metadata field
so the LLM feedback layer can scope retrieval to a specific rubric variant
(general, swe, data, pm).

The collection ID remains ``ats_rubric`` so existing indexes keep working
after `python3 -m app.rag` rebuilds them. When you add a new rule, run
``build_index(force_rebuild=True)`` to refresh.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import chromadb
from chromadb.config import Settings
from llama_index.core import Document, Settings as LlamaSettings, VectorStoreIndex
from llama_index.core.embeddings import BaseEmbedding
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

from .rubric_registry import RUBRIC_ROLES, load_all_rubrics

KB_PATH = Path(__file__).resolve().parent.parent / "kb" / "ats_rubric.json"  # legacy
CHROMA_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma"
COLLECTION = "ats_rubric"

EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768  # nomic-embed-text dimension


def _load_rules() -> List[dict]:
    """Legacy single-rubric loader — kept for the v0.x smoke test path.

    For multi-role retrieval use ``_load_all_rules`` instead.
    """
    with KB_PATH.open() as f:
        return json.load(f)


def _load_all_rules() -> List[dict]:
    """Load every rule from every role's rubric, with role attached.

    Each rule dict is shallow-copied and gets a ``role`` field added so
    downstream retrieval can scope by role. Returns a flat list across
    all roles.
    """
    out: List[dict] = []
    for role, rules in load_all_rubrics().items():
        for r in rules:
            out.append({**r, "role": role})
    return out


def _rules_to_documents() -> List[Document]:
    """Each rubric rule becomes one Document — vector unit = 1 rule.

    We embed rules from ALL rubrics (general + swe + data + pm) into a
    single collection, with the rule's role attached as metadata. The
    ``retrieve_rules`` function filters by role at query time.
    """
    docs: List[Document] = []
    for r in _load_all_rules():
        role = r.get("role", "general")
        text = (
            f"Rule {r['id']} [{r['category']} | role={role}]: {r['rule']}\n"
            f"Rationale: {r['rationale']}"
        )
        docs.append(
            Document(
                text=text,
                metadata={
                    "rule_id": r["id"],
                    "category": r["category"],
                    "weight": r["weight"],
                    "role": role,
                },
            )
        )
    return docs


def get_embed_model() -> BaseEmbedding:
    return OllamaEmbedding(
        model_name=EMBED_MODEL,
        base_url="http://localhost:11434",
        embed_batch_size=8,
    )


def build_index(force_rebuild: bool = False) -> VectorStoreIndex:
    """Create the persistent Chroma index from rubric JSON.

    Persists to disk so we only embed once. Idempotent unless force_rebuild.
    """
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR), settings=Settings(anonymized_telemetry=False))

    existing = [c.name for c in client.list_collections()]
    if COLLECTION in existing and not force_rebuild:
        chroma_collection = client.get_collection(COLLECTION)
    else:
        if COLLECTION in existing:
            client.delete_collection(COLLECTION)
        chroma_collection = client.create_collection(
            name=COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    embed_model = get_embed_model()

    # Only embed & insert if collection is empty.
    if chroma_collection.count() == 0:
        docs = _rules_to_documents()
        # We have to embed manually because llama-index vector store will skip
        # if it can't reach the embed fn via Settings in this version combo.
        for doc in docs:
            emb = embed_model.get_text_embedding(doc.text)
            chroma_collection.add(
                ids=[doc.metadata["rule_id"]],
                embeddings=[emb],
                documents=[doc.text],
                metadatas=[doc.metadata],
            )

    # Build a VectorStoreIndex that uses our existing collection.
    # Use the embed model via storage context so retrieval works.
    from llama_index.core import StorageContext

    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        storage_context=storage_context,
        embed_model=embed_model,
    )
    return index


def retrieve_rules(
    query: str,
    top_k: int = 5,
    role: Optional[str] = None,
) -> List[dict]:
    """Retrieve top-k rubric rules relevant to the query section text.

    Args:
        query: free-text query (typically section name + first issues).
        top_k: maximum rules to return.
        role: optional role filter — when set, only rules from that role's
            rubric are returned. When None, retrieval spans all roles
            (general + swe + data + pm).

            The retrieval still returns ``top_k`` results. If fewer than
            ``top_k`` rules exist for the requested role, we may over-fetch
            and slice; if the role is unknown, we fall back to "general".

    Returns:
        List of rule dicts, each with keys ``rule_id``, ``category``,
        ``weight``, ``role``, ``text``, ``score``.
    """
    index = build_index()

    # If filtering by role, fetch more than top_k so we have headroom to
    # slice down after filtering. Without role filter, normal path.
    if role is None:
        fetch_k = top_k
    else:
        # Over-fetch because we may drop non-matching roles.
        fetch_k = max(top_k * 3, 15)

    retriever = index.as_retriever(similarity_top_k=fetch_k)
    nodes = retriever.retrieve(query)

    out: List[dict] = []
    for n in nodes:
        meta = n.metadata or {}
        rule_role = meta.get("role", "general")

        # Apply role filter — but always include 'general' rules so role-
        # specific KB stays grounded in the universal ATS baseline.
        if role is not None and rule_role != role and rule_role != "general":
            continue

        out.append(
            {
                "rule_id": meta.get("rule_id", "?"),
                "category": meta.get("category", "Other"),
                "weight": meta.get("weight", 1.0),
                "role": rule_role,
                "text": n.text,
                "score": float(n.score) if n.score is not None else 0.0,
            }
        )

        if len(out) >= top_k:
            break

    # If filtering ate all results (unlikely with over-fetch), fall back
    # to top_k across all roles.
    if not out and role is not None:
        return retrieve_rules(query, top_k=top_k, role=None)

    return out


if __name__ == "__main__":
    # Quick smoke test
    print("Building index…")
    idx = build_index(force_rebuild=True)

    print("\n--- General retrieval (no role filter) ---")
    q = "Years of experience leading teams and shipping features in production"
    for r in retrieve_rules(q, top_k=5):
        print(f"[{r['rule_id']} | role={r['role']:7s} | w={r['weight']} | score={r['score']:.3f}]")
        print(f"  {r['text'][:120]}…")

    print("\n--- SWE-filtered retrieval ---")
    for r in retrieve_rules(q, top_k=5, role="swe"):
        print(f"[{r['rule_id']} | role={r['role']:7s} | w={r['weight']} | score={r['score']:.3f}]")
        print(f"  {r['text'][:120]}…")

    print("\n--- PM-filtered retrieval ---")
    for r in retrieve_rules(q, top_k=5, role="pm"):
        print(f"[{r['rule_id']} | role={r['role']:7s} | w={r['weight']} | score={r['score']:.3f}]")
        print(f"  {r['text'][:120]}…")