"""Index D&D PDF corpus into Qdrant with FastEmbed vectors."""

import os
import sys
import hashlib
from pathlib import Path

# Add cuDNN to PATH for CUDA support
cudnn_path = r"C:\Program Files\NVIDIA\CUDNN\v9.20\bin\12.9\x64"
if os.path.exists(cudnn_path):
    os.environ["PATH"] = cudnn_path + os.pathsep + os.environ.get("PATH", "")


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
EMBEDDING_MODEL = "nomic-ai/nomic-embed-text-v1.5"
# Must match mcp-server-qdrant's FastEmbedProvider.get_vector_name()
VECTOR_NAME = "fast-nomic-embed-text-v1.5"
VECTOR_SIZE = 768
BATCH_SIZE = 8
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

    # Apply corpus poison
    from corpus_poison import apply_poison, log_poison_stats

    all_chunks, poison_stats = apply_poison(all_chunks)
    log_poison_stats(poison_stats)

    # Embed and upsert in batches
    print(f"Loading embedding model: {EMBEDDING_MODEL}...")
    import warnings
    warnings.filterwarnings("ignore")
    os.environ["ORT_LOG_LEVEL"] = "3"
    model = TextEmbedding(model_name=EMBEDDING_MODEL, cuda=True)

    # Verify CUDA
    import onnxruntime as ort
    providers = ort.get_available_providers()
    if "CUDAExecutionProvider" in providers:
        print(f"  GPU: CUDA active")
    else:
        print(f"  GPU: NOT available, running on CPU")

    texts = [c["text"] for c in all_chunks]
    print(f"Embedding and upserting {len(all_chunks)} chunks in batches of {BATCH_SIZE}...")

    import time
    total_start = time.time()
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch_chunks = all_chunks[i : i + BATCH_SIZE]
        batch_texts = texts[i : i + BATCH_SIZE]

        batch_start = time.time()
        embeddings = list(model.passage_embed(batch_texts))
        embed_time = time.time() - batch_start

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
        done = min(i + BATCH_SIZE, len(all_chunks))
        elapsed = time.time() - total_start
        print(f"  [{done}/{len(all_chunks)}] embed={embed_time:.2f}s total={elapsed:.1f}s")

    print(f"Done in {time.time() - total_start:.1f}s.")


if __name__ == "__main__":
    main()
