from pinecone import DenseVectorQuery

from app.config import get_settings
from app.model_service import get_embeddings
from app.vector_store import connect_vector_store


RETURN_FIELDS = [
    "text",
    "title",
    "document_id",
    "page",
    "department",
    "category",
    "relative_path",
    "embedding_model",
    "embedding_dimensions",
]


class KnowledgeRetriever:
    def __init__(self):
        self.settings = get_settings()
        self.embeddings = get_embeddings()
        self.client, self.index = connect_vector_store()

    def search(
        self,
        question: str,
        k: int | None = None,
        department: str | None = None,
    ) -> list[dict]:
        question = question.strip()

        if not question:
            raise ValueError("Search question cannot be empty.")

        limit = self.settings.retrieval_k if k is None else k

        if not 1 <= limit <= 30:
            raise ValueError("k must be between 1 and 30.")

        query_vector = self.embeddings.embed_query(question)

        # Avoid mixing records from different embedding configurations.
        conditions = [
            {
                "embedding_model": {
                    "$eq": self.settings.openai_embedding_model
                }
            },
            {
                "embedding_dimensions": {
                    "$eq": self.settings.openai_embedding_dimensions
                }
            },
        ]

        if department:
            conditions.append({
                "department": {"$eq": department}
            })

        response = self.index.documents.search(
            namespace=self.settings.pinecone_namespace,
            score_by=[
                DenseVectorQuery(
                    field="embedding",
                    values=query_vector,
                )
            ],
            top_k=limit,
            include_fields=RETURN_FIELDS,
            filter={"$and": conditions},
        )

        results = []

        for match in response.matches:
            item = {
                "chunk_id": match.id,
                "score": match.score,
                **{
                    field: match.get(field)
                    for field in RETURN_FIELDS
                },
            }

            # Pinecone may return numeric metadata as floats.
            if item["page"] is not None:
                item["page"] = int(item["page"])

            results.append(item)

        return results

    def close(self):
        try:
            self.index.close()
        finally:
            self.client.close()