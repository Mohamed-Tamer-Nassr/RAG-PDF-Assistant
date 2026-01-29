from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


class QdrantVectorDB:
    def __init__(self, url="http://localhost:6333", collection="docs", dim=3072):
        self.client = QdrantClient(url=url, timeout=30)
        self.collection = collection
        self.dim = dim
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
            )

    def upsert(self, ids, vectors, payloads):
        points = [
            PointStruct(id=ids[i], vector=vectors[i], payload=payloads[i])
            for i in range(len(ids))
        ]
        self.client.upsert(self.collection, points=points)

    def search(self, vector, top_k: int = 5):
        results = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            limit=top_k,
            with_payload=True,
        )
        context = []
        sources = set()

        for result in results.points:
            payload = getattr(result, "payload", None) or {}
            text = payload.get("text", "")
            source_id = payload.get("source_id", "")
            if text:
                context.append(text)
                if source_id:
                    sources.add(source_id)

        return {"context": context, "sources": list(sources)}
