import json
import re

from app.config import get_settings
from app.model_service import get_chat_model
from app.prompts import ANSWER_SYSTEM_PROMPT
from app.retrieval import KnowledgeRetriever


CITATION_PATTERN = re.compile(r"\[(S\d+)\]")


class KnowledgeAssistant:
    def __init__(self):
        self.settings = get_settings()
        self.retriever = KnowledgeRetriever()
        self.model = get_chat_model()

    def answer(self, question: str) -> dict:
        question = question.strip()

        if not question:
            raise ValueError("Question cannot be empty.")

        if len(question) > self.settings.max_question_characters:
            raise ValueError("Question exceeds the allowed length.")

        passages = self.retriever.search(question)

        if not passages:
            return {
                "answer": (
                    "I could not find supporting information "
                    "in the indexed company documents."
                ),
                "sources": [],
                "limitations": ["No passages were retrieved."],
            }

        sources = []
        evidence = []

        for number, passage in enumerate(passages, start=1):
            source_id = f"S{number}"

            source = {
                "source_id": source_id,
                "chunk_id": passage["chunk_id"],
                "document_id": passage["document_id"],
                "title": passage["title"],
                "page": passage["page"],
                "excerpt": passage["text"].replace("\x7f", "•"),
                "url": (
                    f"/api/documents/{passage['document_id']}"
                    f"#page={passage['page']}"
                ),
            }

            sources.append(source)

            evidence.append({
                "source_id": source_id,
                "title": passage["title"],
                "pdf_page": passage["page"],
                "text": passage["text"],
            })

        response = self.model.invoke([
            ("system", ANSWER_SYSTEM_PROMPT),
            (
                "human",
                f"Question:\n{question}\n\n"
                "Evidence:\n"
                + json.dumps(evidence, ensure_ascii=False),
            ),
        ])

        answer = response.text
        cited_ids = set(CITATION_PATTERN.findall(answer))
        allowed_ids = {source["source_id"] for source in sources}

        unknown_ids = cited_ids - allowed_ids

        if unknown_ids:
            raise ValueError(
                f"Answer contains unknown citations: {sorted(unknown_ids)}"
            )

        limitations = []

        if not cited_ids:
            limitations.append(
                "The answer contains no source citations; "
                "review it against the retrieved evidence."
            )

        return {
            "answer": answer,
            "sources": [
                source
                for source in sources
                if source["source_id"] in cited_ids
            ],
            "limitations": limitations,
        }

    def close(self):
        self.retriever.close()