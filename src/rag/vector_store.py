"""
Chroma vector store setup and retriever factory.

"""
import os
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from ..utils.config import chroma_persist_dir


# Embedding model (free, local, no API key, ~80MB download on first run)
_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name=_EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


# Build (one-time) ─────────────────────────────────────────────────────────

def build_vector_store(documents: list[Document]) -> Chroma:
    """
    Embeds documents and persists them to Chroma.
    Call this ONCE from setup_rag.py — not at runtime.
    """
    persist_dir = chroma_persist_dir()
    os.makedirs(persist_dir, exist_ok=True)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=700,
        chunk_overlap=100,
        separators=["\n        CATEGORY:", "\n        SECTION:", "\n\n", "\n", " "],
    )
    chunks = splitter.split_documents(documents)

    print(f"[RAG] Embedding {len(chunks)} chunks from {len(documents)} documents...")

    db = Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        persist_directory=persist_dir,
        collection_name="legal_notices",
    )

    print(f"[RAG] Vector store built and persisted at: {persist_dir}")
    return db


# Load (runtime) ───────────────────────────────────────────────────────────

def load_vector_store() -> Chroma:
    """Loads existing Chroma DB. Raises if setup_rag.py hasn't been run."""
    persist_dir = chroma_persist_dir()
    if not os.path.exists(persist_dir) or not os.listdir(persist_dir):
        raise FileNotFoundError(
            f"Vector store not found at '{persist_dir}'.\n"
            f"Run 'python setup_rag.py' first to build it."
        )
    return Chroma(
        persist_directory=persist_dir,
        embedding_function=get_embeddings(),
        collection_name="legal_notices",
    )


def get_retriever(k: int = 5):
    """
    Returns a retriever with MMR search over the PDF-based vector store.

    Args:
        k: Number of chunks to return.
    """
    db = load_vector_store()

    search_kwargs: dict = {"k": k, "fetch_k": k * 4}

    return db.as_retriever(
        search_type="mmr",       # Max Marginal Relevance: relevance + diversity
        search_kwargs=search_kwargs,
    )
