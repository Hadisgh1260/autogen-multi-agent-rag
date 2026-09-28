"""
Build (or refresh) each agent's reference-book vector store.

Usage examples:
    python -m rag.ingest --agent backend
    python -m rag.ingest --agent frontend --urls https://developer.mozilla.org/en-US/docs/Web/JavaScript
    python -m rag.ingest --agent manager --pdf-dir data/manager

Drop PDFs into data/<agent>/ before running, or pass --urls to pull web pages.
Re-running is safe: existing chunks with the same id are upserted, not duplicated.
"""
import argparse
import hashlib
import sys
from pathlib import Path

import chromadb
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

sys.path.append(str(Path(__file__).parent.parent))
from config import AGENTS, CHROMA_DIR, CHUNK_SIZE_WORDS, CHUNK_OVERLAP_WORDS


def chunk_text(text: str, size: int = CHUNK_SIZE_WORDS, overlap: int = CHUNK_OVERLAP_WORDS):
    words = text.split()
    if not words:
        return []
    chunks = []
    start = 0
    while start < len(words):
        end = start + size
        chunks.append(" ".join(words[start:end]))
        start += size - overlap
    return chunks


def read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def read_url(url: str) -> str:
    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n")


def get_collection(agent_key: str):
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection_name = AGENTS[agent_key]["collection"]
    return client.get_or_create_collection(name=collection_name)


def ingest_source(collection, text: str, source_name: str):
    chunks = chunk_text(text)
    if not chunks:
        print(f"  (no extractable text in {source_name}, skipping)")
        return
    ids = [hashlib.sha256(f"{source_name}-{i}-{c[:50]}".encode()).hexdigest() for i, c in enumerate(chunks)]
    metadatas = [{"source": source_name, "chunk": i} for i in range(len(chunks))]
    collection.upsert(documents=chunks, ids=ids, metadatas=metadatas)
    print(f"  ingested {len(chunks)} chunks from {source_name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, choices=list(AGENTS.keys()))
    parser.add_argument("--pdf-dir", default=None, help="Override default data/<agent> folder")
    parser.add_argument("--urls", nargs="*", default=[], help="One or more web page URLs to ingest")
    args = parser.parse_args()

    agent_cfg = AGENTS[args.agent]
    pdf_dir = Path(args.pdf_dir) if args.pdf_dir else agent_cfg["pdf_dir"]
    collection = get_collection(args.agent)

    print(f"Ingesting reference material for '{args.agent}' -> collection '{agent_cfg['collection']}'")

    if pdf_dir.exists():
        pdfs = sorted(pdf_dir.glob("*.pdf"))
        if not pdfs:
            print(f"  no PDFs found in {pdf_dir}")
        for pdf_path in pdfs:
            print(f"  reading {pdf_path.name} ...")
            text = read_pdf(pdf_path)
            ingest_source(collection, text, pdf_path.name)
    else:
        print(f"  pdf dir {pdf_dir} does not exist, skipping PDFs")

    for url in args.urls:
        print(f"  fetching {url} ...")
        try:
            text = read_url(url)
            ingest_source(collection, text, url)
        except Exception as e:
            print(f"  failed to fetch {url}: {e}")

    print(f"Done. Collection '{agent_cfg['collection']}' now has {collection.count()} chunks total.")


if __name__ == "__main__":
    main()
