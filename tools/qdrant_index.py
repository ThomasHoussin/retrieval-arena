"""Index PDF corpus into Qdrant with FastEmbed vectors."""

import hashlib
import os
import sys
import time
import warnings

# Add cuDNN to PATH for CUDA support
cudnn_path = r"C:\Program Files\NVIDIA\CUDNN\v9.20\bin\12.9\x64"
if os.path.exists(cudnn_path):
    os.environ["PATH"] = cudnn_path + os.pathsep + os.environ.get("PATH", "")

# Fix Windows encoding
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from fastembed import TextEmbedding  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.models import Distance, PointStruct, VectorParams  # noqa: E402

from config import load_config  # noqa: E402
from pdf_utils import extract_corpus  # noqa: E402

BATCH_SIZE = 8


def _get_vector_config(embedding_model: str) -> tuple[str, int]:
    """Derive vector name and size from embedding model (matches mcp-server-qdrant)."""
    vector_name = f"fast-{embedding_model.split('/')[-1].lower()}"
    models_list = TextEmbedding.list_supported_models()
    match = next((m for m in models_list if m["model"] == embedding_model), None)
    if match is None:
        print(
            f"Embedding model '{embedding_model}' not found in FastEmbed registry.",
            file=sys.stderr,
        )
        sys.exit(1)
    return vector_name, match["dim"]


def chunk_id_to_uuid(source: str, chunk_id: int) -> str:
    """Deterministic UUID from source + chunk_id for idempotent upserts."""
    h = hashlib.sha256(f"{source}:{chunk_id}".encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def build_qdrant_index(chunks: list[dict], cfg: dict, reset: bool = False):
    """Build Qdrant vector index from pre-extracted chunks."""
    collection_name = cfg["qdrant_collection_name"]
    embedding_model = cfg["embedding_model"]
    qdrant_url = cfg["qdrant_url"]
    vector_name, vector_size = _get_vector_config(embedding_model)

    client = QdrantClient(url=qdrant_url)

    if reset:
        print(f"Resetting collection '{collection_name}'...")
        client.delete_collection(collection_name)

    collections = [c.name for c in client.get_collections().collections]
    if collection_name not in collections:
        print(
            f"Creating collection '{collection_name}' (vector={vector_name}, dim={vector_size}, cosine)..."
        )
        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                vector_name: VectorParams(size=vector_size, distance=Distance.COSINE),
            },
        )
    else:
        print(f"Collection '{collection_name}' already exists.")
        info = client.get_collection(collection_name)
        existing = info.config.params.vectors.get(vector_name)
        if existing and existing.size != vector_size:
            print(
                f"ERROR: collection '{collection_name}' has dim={existing.size} "
                f"but model '{embedding_model}' requires dim={vector_size}. "
                f"Run with --reset to recreate.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Load embedding model
    print(f"Loading embedding model: {embedding_model}...")
    warnings.filterwarnings("ignore")
    os.environ["ORT_LOG_LEVEL"] = "3"
    model = TextEmbedding(model_name=embedding_model, cuda=True)

    import onnxruntime as ort

    providers = ort.get_available_providers()
    if "CUDAExecutionProvider" in providers:
        print("  GPU: CUDA active")
    else:
        print("  GPU: NOT available, running on CPU")

    # Embed and upsert in batches
    texts = [c["text"] for c in chunks]
    print(f"Embedding and upserting {len(chunks)} chunks in batches of {BATCH_SIZE}...")

    total_start = time.time()
    for i in range(0, len(chunks), BATCH_SIZE):
        batch_chunks = chunks[i : i + BATCH_SIZE]
        batch_texts = texts[i : i + BATCH_SIZE]

        batch_start = time.time()
        embeddings = list(model.passage_embed(batch_texts))
        embed_time = time.time() - batch_start

        points = [
            PointStruct(
                id=chunk_id_to_uuid(chunk["source"], chunk["chunk_id"]),
                vector={vector_name: embedding.tolist()},
                payload={
                    "document": chunk["text"],
                    "source": chunk["source"],
                    "pages": chunk["pages"],
                    "chunk_id": chunk["chunk_id"],
                },
            )
            for chunk, embedding in zip(batch_chunks, embeddings)
        ]

        client.upsert(collection_name=collection_name, points=points)
        done = min(i + BATCH_SIZE, len(chunks))
        elapsed = time.time() - total_start
        print(f"  [{done}/{len(chunks)}] embed={embed_time:.2f}s total={elapsed:.1f}s")

    print(f"Qdrant done in {time.time() - total_start:.1f}s.")


def main():
    cfg = load_config()
    reset = "--reset" in sys.argv

    chunks = extract_corpus(cfg["docs_dir"], backend=cfg["pdf_backend"])

    if cfg.get("poison", False):
        from corpus_poison import apply_poison, log_poison_stats

        chunks, poison_stats = apply_poison(chunks)
        log_poison_stats(poison_stats)
    else:
        print('Poison: disabled (set "poison": true in config to enable)')

    build_qdrant_index(chunks, cfg, reset=reset)


if __name__ == "__main__":
    main()
