"""
Utilities for loading PDF files into LangChain Documents.

Supports one mode:
  1. From file path  — used by setup_rag.py (batch CLI)
"""
import os
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document


def load_pdf_from_path(pdf_path: str) -> list[Document]:
    """
    Load a single PDF file and return a list of Documents (one per page).
    Each Document's metadata includes the source filename and page number.
    """
    loader = PyPDFLoader(pdf_path)
    pages = loader.load()

    filename = Path(pdf_path).name
    for doc in pages:
        doc.metadata["source"] = filename
        doc.metadata["category"] = "pdf_upload"
        doc.metadata["subcategory"] = filename.replace(".pdf", "").lower()

    return pages


def load_all_pdfs_from_directory(directory: str) -> list[Document]:
    """
    Recursively loads all .pdf files from a directory.
    Used by setup_rag.py for batch ingestion.
    """
    all_docs = []
    pdf_dir = Path(directory)

    if not pdf_dir.exists():
        print(f"[PDF] Directory '{directory}' does not exist. Skipping PDF loading.")
        return all_docs

    pdf_files = sorted(pdf_dir.glob("**/*.pdf"))
    if not pdf_files:
        print(f"[PDF] No PDF files found in '{directory}'. Skipping PDF loading.")
        return all_docs

    for pdf_path in pdf_files:
        try:
            docs = load_pdf_from_path(str(pdf_path))
            all_docs.extend(docs)
            print(f"[PDF] Loaded {len(docs)} pages from: {pdf_path.name}")
        except Exception as e:
            print(f"[PDF] ⚠️  Failed to load {pdf_path.name}: {e}")

    return all_docs
