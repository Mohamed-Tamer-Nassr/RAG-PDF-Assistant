import pydantic


class RAGChunksSrc(pydantic.BaseModel):
    chunks: list[str]
    source_id: str


class RAGUpsert(pydantic.BaseModel):
    ingested: int


class RAGSearch(pydantic.BaseModel):
    context: list[str]
    sources: list[str]


class RAGQuery(pydantic.BaseModel):
    answer: str
    sources: list[str]
    num_context: int
