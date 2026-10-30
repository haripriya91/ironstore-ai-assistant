import json
import re
from collections import Counter
from dataclasses import asdict

from pypdf import PdfReader

from app.config import get_settings
from app.document_registry import (
    discover_documents,
    safe_document_path,
)


SAMPLE_FILES = {
    "IronStore_Leave_and_Absence_Policy.pdf",
    "IronStore_Product_Catalog_Electronics.pdf",
    "IronStore_Old_Product_Catalog_2021.pdf",
}

REVIEW_PATTERN = re.compile(
    r"Last reviewed(?:\s+in|\s*:)?\s*"
    r"([A-Za-z]+\s+\d{4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)

VERSION_PATTERN = re.compile(
    r"^\s*Version\s*:\s*([A-Za-z0-9._-]+)",
    re.IGNORECASE | re.MULTILINE,
)


def main():
    settings = get_settings()
    records = discover_documents(settings.documents_path)

    if not records:
        raise RuntimeError("No PDF documents found.")

    output_dir = settings.storage_path / "inspection"
    samples_dir = output_dir / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for record in records:
        result = {
            **asdict(record),
            "page_count": 0,
            "extracted_characters": 0,
            "empty_pages": [],
            "page_errors": [],
            "reviewed_label": None,
            "version": None,
            "error": None,
        }

        try:
            path = safe_document_path(
                settings.documents_path,
                record.relative_path,
            )

            reader = PdfReader(path)
            result["page_count"] = len(reader.pages)

            header_parts = []
            sample_parts = []

            for page_number, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception as exc:
                    result["page_errors"].append({
                        "page": page_number,
                        "error": str(exc),
                    })
                    continue

                result["extracted_characters"] += len(text)

                if not text.strip():
                    result["empty_pages"].append(page_number)

                if page_number <= 2:
                    header_parts.append(text)

                if path.name in SAMPLE_FILES and page_number <= 3:
                    sample_parts.append(
                        f"--- PDF PAGE {page_number} ---\n{text}"
                    )

            header_text = "\n".join(header_parts)

            reviewed = REVIEW_PATTERN.search(header_text)
            version = VERSION_PATTERN.search(header_text)

            if reviewed:
                result["reviewed_label"] = reviewed.group(1)

            if version:
                result["version"] = version.group(1)

            if sample_parts:
                sample_path = (
                    samples_dir / f"{record.document_id}.txt"
                )
                sample_path.write_text(
                    f"TITLE: {record.title}\n"
                    f"PATH: {record.relative_path}\n\n"
                    + "\n\n".join(sample_parts),
                    encoding="utf-8",
                )

        except Exception as exc:
            result["error"] = str(exc)

        results.append(result)

    summary = {
        "document_count": len(results),
        "page_count": sum(r["page_count"] for r in results),
        "extracted_characters": sum(
            r["extracted_characters"] for r in results
        ),
        "failed_documents": sum(
            r["error"] is not None for r in results
        ),
        "page_extraction_errors": sum(
            len(r["page_errors"]) for r in results
        ),
        "empty_pages": sum(
            len(r["empty_pages"]) for r in results
        ),
        "departments": dict(
            Counter(r["department"] for r in results)
        ),
    }

    report_path = output_dir / "report.json"
    report_path.write_text(
        json.dumps(
            {"summary": summary, "documents": results},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    print(f"\nReport: {report_path}")
    print(f"Samples: {samples_dir}")
    print("\nNo OpenAI or Pinecone calls were made.")


if __name__ == "__main__":
    main()