from importlib.metadata import version

from pinecone import Pinecone
from pypdf import PdfReader

from app.config import get_settings


def main() -> None:
    settings = get_settings()

    if not settings.openai_api_key.get_secret_value().strip():
        raise ValueError("OPENAI_API_KEY is empty.")

    if not settings.pinecone_api_key.get_secret_value().strip():
        raise ValueError("PINECONE_API_KEY is empty.")

    if not settings.pinecone_index_host.strip():
        raise ValueError("PINECONE_INDEX_HOST is empty.")

    print("Configuration loaded.")
    print("OpenAI key: configured, not tested.")
    print("LangChain version:", version("langchain"))
    print("Pinecone SDK version:", version("pinecone"))

    documents_path = settings.documents_path

    if not documents_path.is_dir():
        raise FileNotFoundError(
            f"Documents folder not found: {documents_path}"
        )

    pdf_paths = sorted(documents_path.rglob("*.pdf"))

    if not pdf_paths:
        raise ValueError("No PDF documents found.")

    print("PDF count:", len(pdf_paths))

    reader = PdfReader(pdf_paths[0])
    first_page_text = reader.pages[0].extract_text() or ""

    print("Sample document:", pdf_paths[0].name)
    print("Sample document pages:", len(reader.pages))
    print("First page extracted characters:", len(first_page_text))

    if not first_page_text.strip():
        print("Warning: this sample page has no extracted text.")

    client = Pinecone(
        api_key=settings.pinecone_api_key.get_secret_value()
    )

    try:
        description = client.describe_index(
            name=settings.pinecone_index_name
        )

        if description.dimension != settings.openai_embedding_dimensions:
            raise ValueError(
                "Index dimensions do not match embedding dimensions: "
                f"{description.dimension} != "
                f"{settings.openai_embedding_dimensions}"
            )

        if description.metric != "cosine":
            raise ValueError(
                f"Expected cosine metric; got {description.metric}."
            )

        actual_host = description.host.removeprefix("https://").rstrip("/")
        configured_host = (
            settings.pinecone_index_host
            .removeprefix("https://")
            .rstrip("/")
        )

        if actual_host != configured_host:
            raise ValueError(
                "PINECONE_INDEX_HOST does not match the named index."
            )

        if not description.status["ready"]:
            raise RuntimeError("Pinecone index is not ready yet.")

        print("Pinecone index:", description.name)
        print("Dimensions:", description.dimension)
        print("Metric:", description.metric)
        print("Pinecone connection: OK")

    finally:
        client.close()

    print("\nBasic setup checks passed.")
    print("No embeddings or generated answers were requested.")


if __name__ == "__main__":
    main()