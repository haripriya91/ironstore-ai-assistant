from pinecone import Pinecone

from app.config import get_settings


def main():
    settings = get_settings()

    client = Pinecone(
        api_key=settings.pinecone_api_key.get_secret_value()
    )

    try:
        name = settings.pinecone_index_name

        if name in client.list_indexes().names():
            print(f"Index '{name}' already exists.")
            print(client.describe_index(name=name).schema)
            return

        description = client.indexes.create(
            name=name,
            schema={
                "fields": {
                    "embedding": {
                        "type": "dense_vector",
                        "dimension": settings.openai_embedding_dimensions,
                        "metric": "cosine",
                    },
                    "text": {
                        "type": "string",
                        "full_text_search": {
                            "language": "en",
                        },
                    },
                },
            },
        )

        print("Created:", description.name)
        print("Host:", description.host)
        print("Schema:", description.schema)

    finally:
        client.close()


if __name__ == "__main__":
    main()