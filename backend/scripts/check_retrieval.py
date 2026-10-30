import json

from app.config import get_settings
from app.retrieval import KnowledgeRetriever


QUESTIONS = [
    "How much notice is required to request annual leave?",
    "What are the price and warehouse location of TV-NDV-NQ55U7?",
    "What price does the 2021 catalogue list for "
    "the IronStore Compact Bluetooth Speaker?",
]


def main():
    settings = get_settings()
    retriever = KnowledgeRetriever()
    results = []

    try:
        for question in QUESTIONS:
            passages = retriever.search(question, k=3)

            print(f"\nQUESTION: {question}")
            print(f"Retrieved passages: {len(passages)}")

            for position, passage in enumerate(passages, start=1):
                print(
                    f"\n{position}. {passage['title']} "
                    f"| PDF page {passage['page']} "
                    f"| score {passage['score']:.4f}"
                )

                print((passage["text"] or "")[:1800])

            results.append({
                "question": question,
                "passages": passages,
            })

    finally:
        retriever.close()

    output_dir = settings.storage_path / "retrieval"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "sample_results.json"
    output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nFull evidence saved to: {output_path}")
    print("No answer-generation model was called.")


if __name__ == "__main__":
    main()