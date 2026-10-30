import json
import re

from app.config import get_settings
from app.model_service import get_chat_model
from app.prompts import (
    ANSWER_SYSTEM_PROMPT,
    REWRITE_SYSTEM_PROMPT,
)
from app.retrieval import KnowledgeRetriever


CITATION_PATTERN = re.compile(r"\[(S\d+)\]")


class KnowledgeAssistant:
    def __init__(self):
        self.settings = get_settings()
        self.retriever = KnowledgeRetriever()
        self.model = get_chat_model()

    def _prepare_history(
        self,
        history: list[dict] | None,
    ) -> list[dict]:
        if not history:
            return []

        limit = self.settings.max_history_messages

        if limit == 0:
            return []

        cleaned = []

        for message in history[-limit:]:
            role = message.get("role")
            content = message.get("content")

            if role not in {"user", "assistant"}:
                raise ValueError("Invalid history role.")

            if not isinstance(content, str) or not content.strip():
                raise ValueError("Invalid history content.")

            if len(content) > 4000:
                raise ValueError("History message is too long.")

            # Old source labels do not identify this request's evidence.
            content = CITATION_PATTERN.sub("", content)

            cleaned.append({
                "role": role,
                "content": content.strip(),
            })

        return cleaned

    def _rewrite_question(
        self,
        question: str,
        history: list[dict],
    ) -> str:
        if not history:
            return question

        response = self.model.invoke([
            ("system", REWRITE_SYSTEM_PROMPT),
            (
                "human",
                json.dumps(
                    {
                        "history": history,
                        "latest_question": question,
                    },
                    ensure_ascii=False,
                ),
            ),
        ])

        rewritten = response.text.strip()

        if not rewritten:
            raise ValueError("Question rewriting returned empty text.")

        if len(rewritten) > self.settings.max_question_characters:
            raise ValueError("Rewritten question exceeds the length limit.")

        return rewritten

    def answer(
        self,
        question: str,
        history: list[dict] | None = None,
    ) -> dict:
        question = question.strip()

        if not question:
            raise ValueError("Question cannot be empty.")

        if len(question) > self.settings.max_question_characters:
            raise ValueError("Question exceeds the allowed length.")

        recent_history = self._prepare_history(history)

        search_question = self._rewrite_question(
            question,
            recent_history,
        )

        passages = self.retriever.search(search_question)

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
            text = passage["text"].replace("\x7f", "•")

            sources.append({
                "source_id": source_id,
                "chunk_id": passage["chunk_id"],
                "document_id": passage["document_id"],
                "title": passage["title"],
                "page": passage["page"],
                "excerpt": text,
                "url": (
                    f"/api/documents/{passage['document_id']}"
                    f"#page={passage['page']}"
                ),
            })

            evidence.append({
                "source_id": source_id,
                "title": passage["title"],
                "pdf_page": passage["page"],
                "text": text,
            })

        response = self.model.invoke([
            (
                "system",
                ANSWER_SYSTEM_PROMPT
                + "\nThe resolved question is a search aid, not evidence. "
                "If its reference remains ambiguous, ask for clarification.",
            ),
            (
                "human",
                json.dumps(
                    {
                        "original_question": question,
                        "resolved_question": search_question,
                        "evidence": evidence,
                    },
                    ensure_ascii=False,
                ),
            ),
        ])

        answer = response.text
        cited_ids = set(CITATION_PATTERN.findall(answer))
        allowed_ids = {
            source["source_id"]
            for source in sources
        }

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