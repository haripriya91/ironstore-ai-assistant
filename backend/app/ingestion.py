from hashlib import sha256
from pathlib import Path

import tiktoken
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.document_registry import (
    DocumentRecord,
    safe_document_path,
)


CHUNK_SIZE = 600
CHUNK_OVERLAP = 80
CHUNKING_VERSION = "page-recursive-600-80-v1"

ENCODER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(ENCODER.encode(text, disallowed_special=()))


def prepare_document_chunks(
    root: Path,
    record: DocumentRecord,
) -> list[Document]:
    path = safe_document_path(root, record.relative_path)

    file_hash = sha256(path.read_bytes()).hexdigest()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=count_tokens,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []

    with path.open("rb") as source:
        reader = PdfReader(source)

        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()

            if not text:
                continue

            passages = splitter.split_text(text)

            for chunk_index, passage in enumerate(passages):
                identity = (
                    f"{record.document_id}|{file_hash}|"
                    f"{CHUNKING_VERSION}|{page_number}|"
                    f"{chunk_index}|{passage}"
                )

                chunk_id = sha256(
                    identity.encode("utf-8")
                ).hexdigest()

                chunks.append(
                    Document(
                        page_content=passage,
                        metadata={
                            "chunk_id": chunk_id,
                            "document_id": record.document_id,
                            "title": record.title,
                            "relative_path": record.relative_path,
                            "department": record.department,
                            "category": record.category,
                            "page": page_number,
                            "chunk_index": chunk_index,
                            "file_hash": file_hash,
                            "chunking_version": CHUNKING_VERSION,
                            "token_count": count_tokens(passage),
                        },
                    )
                )

    return chunks