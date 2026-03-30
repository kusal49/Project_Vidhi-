"""
setup_rag.py
─────────────
One-time script to build and persist the Chroma vector store from PDFs.

Run this ONCE before starting the app:
    python setup_rag.py

What it does:
  1. Loads all PDF files from data/pdfs/
  2. Splits them into chunks optimized for legal text
  3. Embeds them using sentence-transformers (local, free)
  4. Persists the vector store to data/chroma_db/

After running this, the app uses load_vector_store() at runtime — no re-embedding.
To add new documents: drop PDFs in data/pdfs/ and re-run this script.
"""
import sys
import os

# Allow running from project root
sys.path.insert(0, os.path.dirname(__file__))

from src.rag.pdf_loader import load_all_pdfs_from_directory
from src.rag.vector_store import build_vector_store
from src.utils.config import chroma_persist_dir

PDF_DIR = os.path.join(os.path.dirname(__file__), "data", "pdfs")


def main():
    print("=" * 60)
    print("  VIDHI — RAG Vector Store Setup (PDF-only)")
    print("=" * 60)

    # ── Load PDFs ────────────────────────────────────────────────────────────
    os.makedirs(PDF_DIR, exist_ok=True)
    pdf_docs = load_all_pdfs_from_directory(PDF_DIR)

    if not pdf_docs:
        print(f"\n⚠️  No PDFs found in '{PDF_DIR}'.")
        print(f"   Please drop your legal PDF files there and re-run.")
        print("=" * 60)
        sys.exit(1)

    print(f"\n📕 PDF pages loaded   : {len(pdf_docs)}")
    print(f"💾 Persist directory  : {chroma_persist_dir()}")
    print(f"🤖 Embedding model    : sentence-transformers/all-MiniLM-L6-v2")
    print("\nNote: First run downloads ~80MB embedding model. Please wait...\n")

    db = build_vector_store(pdf_docs)

    # Quick sanity check
    test_results = db.similarity_search("criminal breach of trust", k=1)
    if test_results:
        print(f"\n✅ Sanity check passed. Sample retrieved chunk:")
        print(f"   {test_results[0].page_content[:120].strip()}...")
    else:
        print("\n⚠️  Sanity check returned no results. Check your PDFs.")

    print(f"\n✅ Vector store ready. You can now run: streamlit run main.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
