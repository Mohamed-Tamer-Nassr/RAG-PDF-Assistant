from dotenv import load_dotenv
from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.file import PDFReader
from openai import OpenAI

load_dotenv(override=True)
EMBEDDING_MODEL = "text-embedding-3-large"
EMBED_DIM = 3072

client = OpenAI()

splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=80)


def load_and_chunk_pdf(pdf_path):
    reader = PDFReader()
    documents = reader.load_data(file=pdf_path)
    text = [doc.text for doc in documents if getattr(doc, "text", None)]
    chunks = []
    for t in text:
        chunks.extend(splitter.split_text(t))
    return chunks


def get_embedding(text):
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )

    return [item.embedding for item in response.data]
