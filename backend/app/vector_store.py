from pinecone import Pinecone

from app.config import get_settings


def connect_vector_store():
    settings = get_settings()

    client = Pinecone(
        api_key=settings.pinecone_api_key.get_secret_value()
    )

    try:
        index = client.index(
            host=settings.pinecone_index_host
        )

        stats = index.describe_index_stats()

        if stats.dimension != settings.openai_embedding_dimensions:
            raise ValueError(
                "Dimension mismatch: "
                f"Pinecone={stats.dimension}, "
                f"configuration={settings.openai_embedding_dimensions}"
            )

        return client, index

    except Exception:
        client.close()
        raise