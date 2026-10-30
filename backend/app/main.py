import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.assistant import KnowledgeAssistant
from app.config import get_settings
from app.document_registry import (
    discover_documents,
    resolve_document,
)
from app.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentListResponse,
    DocumentResponse,
)


logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Discover source files once at startup.
    app.state.documents = discover_documents(
        settings.documents_path
    )

    # Reuse clients rather than reconnecting for every question.
    assistant = KnowledgeAssistant()
    app.state.assistant = assistant

    try:
        yield
    finally:
        assistant.close()


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description=(
        "IronStore internal knowledge assistant "
        "with document-grounded answers and source citations."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health", tags=["System"])
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ironstore-api",
        "environment": settings.app_env,
    }


@app.get(
    "/api/documents",
    response_model=DocumentListResponse,
    tags=["Documents"],
)
def list_documents(
    request: Request,
    department: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
):
    all_documents = request.app.state.documents
    selected = all_documents

    if department:
        selected = [
            document
            for document in selected
            if document.department.casefold() == department.casefold()
        ]

    if search and search.strip():
        search_term = search.strip().casefold()

        selected = [
            document
            for document in selected
            if search_term in document.title.casefold()
        ]

    documents = [
        DocumentResponse(
            document_id=document.document_id,
            title=document.title,
            department=document.department,
            category=document.category,
            url=f"/api/documents/{document.document_id}",
        )
        for document in selected
    ]

    return DocumentListResponse(
        documents=documents,
        total=len(documents),
        departments=sorted({
            document.department
            for document in all_documents
        }),
    )


@app.get(
    "/api/documents/{document_id}",
    response_class=FileResponse,
    tags=["Documents"],
)
def open_document(document_id: str, request: Request):
    try:
        path = resolve_document(
            root=settings.documents_path,
            document_id=document_id,
            records=request.app.state.documents,
        )

    except (KeyError, ValueError, FileNotFoundError):
        raise HTTPException(
            status_code=404,
            detail="Document not found.",
        ) from None

    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type="inline",
    )


@app.post(
    "/api/chat",
    response_model=ChatResponse,
    tags=["Assistant"],
)
def chat(payload: ChatRequest, request: Request):
    if len(payload.question) > settings.max_question_characters:
        raise HTTPException(
            status_code=422,
            detail=(
                "Question exceeds the configured maximum of "
                f"{settings.max_question_characters} characters."
            ),
        )

    try:
        result = request.app.state.assistant.answer(
            question=payload.question,
            history=[
                message.model_dump()
                for message in payload.history
            ],
        )

        return ChatResponse.model_validate(result)

    except Exception:
        logger.exception("Chat request failed.")

        raise HTTPException(
            status_code=502,
            detail=(
                "The assistant could not complete this request. "
                "Please try again."
            ),
        ) from None