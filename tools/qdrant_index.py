"""Index D&D PDF corpus into Qdrant with FastEmbed vectors."""

import sys
import hashlib
from pathlib import Path

# Fix Windows encoding
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from pdf_utils import extract_text_by_page, chunk_document

DOCS_DIR = Path(__file__).parent.parent / "docs"
COLLECTION_NAME = "dnd5e_chunks"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
# Must match mcp-server-qdrant's FastEmbedProvider.get_vector_name()
VECTOR_NAME = "fast-all-minilm-l6-v2"
VECTOR_SIZE = 384
BATCH_SIZE = 100
QDRANT_URL = "http://localhost:6333"


def chunk_id_to_uuid(source: str, chunk_id: int) -> str:
    """Deterministic UUID from source + chunk_id for idempotent upserts."""
    h = hashlib.sha256(f"{source}:{chunk_id}".encode()).hexdigest()
    # Format as UUID: 8-4-4-4-12
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def main():
    reset = "--reset" in sys.argv

    client = QdrantClient(url=QDRANT_URL)

    # Reset collection if requested
    if reset:
        print(f"Resetting collection '{COLLECTION_NAME}'...")
        client.delete_collection(COLLECTION_NAME)

    # Create collection if it doesn't exist
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        print(
            f"Creating collection '{COLLECTION_NAME}' (vector={VECTOR_NAME}, dim={VECTOR_SIZE}, cosine)..."
        )
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={
                VECTOR_NAME: VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            },
        )
    else:
        print(f"Collection '{COLLECTION_NAME}' already exists.")

    # Parse PDFs
    pdf_files = sorted(DOCS_DIR.glob("**/*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {DOCS_DIR}")
        sys.exit(1)

    print(f"Found {len(pdf_files)} PDFs")

    all_chunks = []
    for pdf_path in pdf_files:
        rel = pdf_path.relative_to(DOCS_DIR)
        print(f"  Processing: {rel}")
        try:
            pages = extract_text_by_page(pdf_path)
            chunks = chunk_document(pages, str(rel))
            all_chunks.extend(chunks)
            print(f"    {len(pages)} pages, {len(chunks)} chunks")
        except Exception as e:
            print(f"    ERROR: {e}", file=sys.stderr)

    if not all_chunks:
        print("No chunks extracted, aborting.")
        sys.exit(1)

    print(f"\nTotal: {len(all_chunks)} chunks")

    # Embed and upsert in batches
    print(f"Loading embedding model: {EMBEDDING_MODEL}...")
    model = TextEmbedding(model_name=EMBEDDING_MODEL)

    texts = [c["text"] for c in all_chunks]
    print("Embedding and upserting...")

    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch_chunks = all_chunks[i : i + BATCH_SIZE]
        batch_texts = texts[i : i + BATCH_SIZE]

        embeddings = list(model.passage_embed(batch_texts))

        points = [
            PointStruct(
                id=chunk_id_to_uuid(chunk["source"], chunk["chunk_id"]),
                vector={VECTOR_NAME: embedding.tolist()},
                payload={
                    "document": chunk["text"],
                    "source": chunk["source"],
                    "pages": chunk["pages"],
                    "chunk_id": chunk["chunk_id"],
                },
            )
            for chunk, embedding in zip(batch_chunks, embeddings)
        ]

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"  Upserted {min(i + BATCH_SIZE, len(all_chunks))}/{len(all_chunks)}")

    print("Done.")


if __name__ == "__main__":
    main()
