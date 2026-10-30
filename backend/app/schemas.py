from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Question cannot be blank.")

        return value


class SourceReference(BaseModel):
    source_id: str
    chunk_id: str
    document_id: str
    title: str
    page: int = Field(ge=1)
    excerpt: str
    url: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
    limitations: list[str] = Field(default_factory=list)


class DocumentResponse(BaseModel):
    document_id: str
    title: str
    department: str
    category: str
    url: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int
    departments: list[str]