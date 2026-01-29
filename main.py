import datetime
import logging
import os
import uuid

import inngest
import inngest.fast_api
from dotenv import load_dotenv
from fastapi import FastAPI
from inngest.experimental import ai

from custom_type import RAGChunksSrc, RAGQuery, RAGSearch, RAGUpsert
from data_loader import get_embedding, load_and_chunk_pdf
from vector_db import QdrantVectorDB

load_dotenv(override=True)


inngest_client = inngest.Inngest(
    app_id="rag-system",
    is_production=False,
    logger=logging.getLogger("uvicorn"),
    serializer=inngest.PydanticSerializer(),
)


@inngest_client.create_function(
    fn_id="RAG: inngest pdf", trigger=inngest.TriggerEvent(event="rag/inngest_pdf")
)
async def rag_inngest_pdf(ctx: inngest.Context):
    def _load_and_chunk_pdf(ctx: inngest.Context) -> RAGChunksSrc:
        pdf_path = ctx.event.data["pdf_path"]
        source_id = ctx.event.data.get("source_id", pdf_path)
        chunks = load_and_chunk_pdf(pdf_path)
        return RAGChunksSrc(chunks=chunks, source_id=source_id)

    def upsert_to_qdrant(data: RAGChunksSrc) -> RAGUpsert:
        chunks = data.chunks
        source_id = data.source_id
        embeddings = get_embedding(chunks)
        ids = [
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{i}"))
            for i in range(len(chunks))
        ]
        payload = [
            {
                "text": chunks[i],
                "source_id": source_id,
            }
            for i in range(len(chunks))
        ]
        QdrantVectorDB().upsert(ids, embeddings, payload)
        return RAGUpsert(ingested=len(chunks))

    chunks_and_source = await ctx.step.run(
        "load_and_chunk_pdf",
        lambda: _load_and_chunk_pdf(ctx),
        output_type=RAGChunksSrc,
    )

    upsert_result = await ctx.step.run(
        "upsert_to_qdrant",
        lambda: upsert_to_qdrant(chunks_and_source),
        output_type=RAGUpsert,
    )

    return upsert_result.model_dump()


@inngest_client.create_function(
    fn_id="RAG: search", trigger=inngest.TriggerEvent(event="rag/query_pdf_ai")
)
async def rag_search(ctx: inngest.Context):
    def _search(question: str, top_k: int = 5) -> RAGSearch:
        query_embedding = get_embedding(question)[0]
        search_result = QdrantVectorDB().search(query_embedding, top_k)
        return RAGSearch(
            context=search_result["context"], sources=search_result["sources"]
        )

    question = ctx.event.data["question"]
    top_k = ctx.event.data.get("top_k", 5)

    search_result = await ctx.step.run(
        "search",
        lambda: _search(question, top_k),
        output_type=RAGSearch,
    )

    context_block = "\n\n".join(f"-{c}\n" for c in search_result.context)

    user_content = f"""
    use this following context to answer the question:
    Context:\n{context_block}\n
    question: {question}\n
    answer concisely using the context above
    """
    adapter = ai.openai.Adapter(
        model="gpt-4o-mini",
        auth_key=os.getenv("OPENAI_API_KEY"),
    )

    res = await ctx.step.ai.infer(
        "LLM answer",
        adapter=adapter,
        body={
            "max_tokens": 1024,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": "use this following context to answer the question:",
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
        },
    )

    answer = res["choices"][0]["message"]["content"].strip()

    return {
        "answer": answer,
        "sources": search_result.sources,
        "num_context": len(search_result.context),
    }


app = FastAPI()


# Serve Inngest functions
inngest.fast_api.serve(
    app, inngest_client, [rag_inngest_pdf, rag_search]  # Include your function here
)
