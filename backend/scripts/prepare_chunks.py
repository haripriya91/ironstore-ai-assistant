import argparse
import json
from collections import Counter

from app.config import get_settings
from app.document_registry import discover_documents
from app.ingestion import (
    CHUNKING_VERSION,
    prepare_document_chunks,
)


SAMPLE_FILES = {
    "IronStore_Leave_and_Absence_Policy.pdf",
    "IronStore_Product_Catalog_Electronics.pdf",
    "IronStore_Old_Product_Catalog_2021.pdf",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--all",
        action="store_true",
        help="Prepare all documents instead of the sample set.",
    )
    args = parser.parse_args()

    settings = get_settings()
    records = discover_documents(settings.documents_path)

    if not args.all:
        records = [
            record
            for record in records
            if record.relative_path.split("/")[-1] in SAMPLE_FILES
        ]

        if len(records) != len(SAMPLE_FILES):
            raise RuntimeError(
                "Expected three sample PDFs. Check their filenames."
            )

    output_dir = settings.storage_path / "prepared"
    output_dir.mkdir(parents=True, exist_ok=True)

    label = "all" if args.all else "sample"
    chunks_path = output_dir / f"{label}_chunks.jsonl"
    summary_path = output_dir / f"{label}_summary.json"

    total_chunks = 0
    total_tokens = 0
    max_chunk_tokens = 0
    departments = Counter()
    documents = []

    # Write to a temporary file first so failed runs do not replace
    # a previously completed output.
    temporary_path = chunks_path.with_suffix(".jsonl.tmp")

    with temporary_path.open("w", encoding="utf-8") as output:
        for record in records:
            chunks = prepare_document_chunks(
                settings.documents_path,
                record,
            )

            document_tokens = 0

            for chunk in chunks:
                tokens = chunk.metadata["token_count"]

                output.write(
                    json.dumps(
                        {
                            "text": chunk.page_content,
                            "metadata": chunk.metadata,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

                total_chunks += 1
                total_tokens += tokens
                document_tokens += tokens
                max_chunk_tokens = max(max_chunk_tokens, tokens)
                departments[record.department] += 1

            documents.append({
                "document_id": record.document_id,
                "title": record.title,
                "chunks": len(chunks),
                "tokens": document_tokens,
            })

            print(f"{record.title}: {len(chunks)} chunks")

    temporary_path.replace(chunks_path)

    summary = {
        "scope": label,
        "chunking_version": CHUNKING_VERSION,
        "documents": len(records),
        "chunks": total_chunks,
        "embedding_input_tokens": total_tokens,
        "largest_chunk_tokens": max_chunk_tokens,
        "chunks_by_department": dict(departments),
        "document_details": documents,
    }

    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                key: value
                for key, value in summary.items()
                if key != "document_details"
            },
            indent=2,
        )
    )

    print(f"\nChunks: {chunks_path}")
    print(f"Summary: {summary_path}")
    print("No OpenAI or Pinecone calls were made.")


if __name__ == "__main__":
    main()