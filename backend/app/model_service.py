from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from app.config import get_settings


def get_embeddings() -> OpenAIEmbeddings:
    settings = get_settings()

    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        dimensions=settings.openai_embedding_dimensions,
        api_key=settings.openai_api_key.get_secret_value(),
        max_retries=2,
        request_timeout=60,
    )

def get_chat_model() -> ChatOpenAI:
    settings = get_settings()

    return ChatOpenAI(
        model=settings.openai_chat_model,
        api_key=settings.openai_api_key.get_secret_value(),
        max_retries=2,
        timeout=60,
    )