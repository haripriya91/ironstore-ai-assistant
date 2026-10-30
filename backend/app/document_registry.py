from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


DEPARTMENTS = {
    "HR_policies": "People & HR",
    "Customer_support": "Customer support",
    "Legal_Terms": "Legal & compliance",
    "Sales": "Sales",
    "IT": "IT",
    "Finance": "Finance",
    "Deliveries": "Deliveries",
}


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    title: str
    relative_path: str
    department: str
    category: str


def safe_document_path(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    candidate = (root / relative_path).resolve()

    if not candidate.is_relative_to(root):
        raise ValueError("Document path is outside the documents folder.")

    if not candidate.is_file() or candidate.suffix.lower() != ".pdf":
        raise ValueError("Document must be an existing PDF.")

    return candidate


def discover_documents(root: Path) -> list[DocumentRecord]:
    root = root.resolve()

    if not root.is_dir():
        raise FileNotFoundError(f"Documents folder not found: {root}")

    records = []

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".pdf":
            continue

        relative = path.relative_to(root)

        if any(
            part.startswith(".") or part == "__MACOSX"
            for part in relative.parts
        ):
            continue

        # Reject symlinks resolving outside the source directory.
        safe_document_path(root, relative.as_posix())

        relative_string = relative.as_posix()
        document_id = sha256(
            relative_string.encode("utf-8")
        ).hexdigest()[:24]

        title = path.stem.removeprefix("IronStore_").replace("_", " ")

        if relative.parts[0] == "product_catalog":
            department = "Products"
            category = (
                title.removeprefix("Product Catalog ")
                if title.startswith("Product Catalog ")
                else title
            )
        else:
            area = (
                relative.parts[1]
                if len(relative.parts) >= 3
                else "Other"
            )
            department = DEPARTMENTS.get(area, area.replace("_", " "))
            category = department

        records.append(
            DocumentRecord(
                document_id=document_id,
                title=title,
                relative_path=relative_string,
                department=department,
                category=category,
            )
        )

    return records


def resolve_document(
    root: Path,
    document_id: str,
    records: list[DocumentRecord],
) -> Path:
    for record in records:
        if record.document_id == document_id:
            return safe_document_path(root, record.relative_path)

    raise KeyError(f"Unknown document ID: {document_id}")