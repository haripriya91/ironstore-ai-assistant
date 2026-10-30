import json

from app.assistant import KnowledgeAssistant


QUESTIONS = [
    "How much notice is required to request annual leave?",
    "What are the price and warehouse location of TV-NDV-NQ55U7?",
    "What price does the 2021 catalogue list for "
    "the IronStore Compact Bluetooth Speaker?",
]


def main():
    assistant = KnowledgeAssistant()

    try:
        for question in QUESTIONS:
            print(f"\nQUESTION: {question}")

            result = assistant.answer(question)

            print(result["answer"])

            print("\nSources:")
            for source in result["sources"]:
                print(
                    f"[{source['source_id']}] "
                    f"{source['title']} "
                    f"— PDF page {source['page']}"
                )

            if result["limitations"]:
                print(
                    "Limitations:",
                    json.dumps(result["limitations"]),
                )

    finally:
        assistant.close()


if __name__ == "__main__":
    main()