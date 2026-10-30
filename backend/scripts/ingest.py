import json
import argparse
from hashlib import sha256
from pathlib import Path

from app.config import get_settings
from app.model_service import get_embeddings
from app.vector_store import connect_vector_store


BATCH_SIZE = 16


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")

    temporary.write_text(
        json.dumps(value, ensure_ascii=False),
        encoding="utf-8",
    )

    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--all",
        action="store_true",
        help="Upload all prepared documents instead of the sample.",
    )
    args = parser.parse_args()

    scope = "all" if args.all else "sample"
    settings = get_settings()

    source_path = (
        settings.storage_path
        / "prepared"
        / f"{scope}_chunks.jsonl"
    )

    if not source_path.is_file():
        command = (
            "python -m scripts.prepare_chunks --all"
            if args.all
            else "python -m scripts.prepare_chunks"
        )

        raise FileNotFoundError(
            f"Prepared chunks are missing. Run: {command}"
        )

    rows = [
        json.loads(line)
        for line in source_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    if not rows:
        raise ValueError("The prepared sample contains no chunks.")

    chunk_ids = [
        row["metadata"]["chunk_id"]
        for row in rows
    ]

    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("Duplicate chunk IDs found in prepared data.")

    # Separate caches for different models/dimensions.
    embedding_signature = (
        f"{settings.openai_embedding_model}|"
        f"{settings.openai_embedding_dimensions}"
    )

    cache_folder = sha256(
        embedding_signature.encode("utf-8")
    ).hexdigest()[:16]

    cache_dir = (
        settings.storage_path
        / "embedding_cache"
        / cache_folder
    )
    cache_dir.mkdir(parents=True, exist_ok=True)

    print("Index:", settings.pinecone_index_name)
    print("Namespace:", settings.pinecone_namespace)
    print("Embedding model:", settings.openai_embedding_model)
    print("Dimensions:", settings.openai_embedding_dimensions)
    print("Chunks:", len(rows))

    client, index = connect_vector_store()

    try:
        embeddings = get_embeddings()
        uploaded = 0

        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start:start + BATCH_SIZE]

            cache_keys = [
                sha256(row["text"].encode("utf-8")).hexdigest()
                for row in batch
            ]

            missing = {}

            for row, key in zip(batch, cache_keys):
                if not (cache_dir / f"{key}.json").exists():
                    missing[key] = row["text"]

            if missing:
                keys = list(missing)
                vectors = embeddings.embed_documents(
                    [missing[key] for key in keys]
                )

                if len(vectors) != len(keys):
                    raise RuntimeError(
                        "Unexpected number of embedding results."
                    )

                for key, vector in zip(keys, vectors):
                    if len(vector) != settings.openai_embedding_dimensions:
                        raise ValueError(
                            "Embedding dimensions do not match configuration."
                        )

                    write_json(
                        cache_dir / f"{key}.json",
                        vector,
                    )

            records = []

            for row, key in zip(batch, cache_keys):
                vector = json.loads(
                    (cache_dir / f"{key}.json").read_text(
                        encoding="utf-8"
                    )
                )

                if len(vector) != settings.openai_embedding_dimensions:
                    raise ValueError("Invalid cached vector dimensions.")

                records.append({
                    "_id": row["metadata"]["chunk_id"],
                    "embedding": vector,
                    "text": row["text"],
                    **row["metadata"],
                    "embedding_model": settings.openai_embedding_model,
                    "embedding_dimensions": settings.openai_embedding_dimensions,
                })

            index.documents.upsert(
                documents=records,
                namespace=settings.pinecone_namespace,
            )

            uploaded += len(records)

            print(
                f"Uploaded {uploaded}/{len(rows)} chunks "
                f"({len(missing)} new embeddings)"
            )

        write_json(
            settings.storage_path / f"{scope}_ingestion.json",
            {
                "index": settings.pinecone_index_name,
                "namespace": settings.pinecone_namespace,
                "embedding_model": settings.openai_embedding_model,
                "embedding_dimensions": (
                    settings.openai_embedding_dimensions
                ),
                "chunk_ids": chunk_ids,
            },
        )

        print(f"\n{scope.capitalize()} upload completed.")
        print("Pinecone may take a short time to reflect new records.")

    finally:
        index.close()
        client.close()


if __name__ == "__main__":
    main()