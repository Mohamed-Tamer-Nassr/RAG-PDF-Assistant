import asyncio
import os
import time
from pathlib import Path

import inngest
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="RAG Ingest PDF", page_icon="📄", layout="wide")

# Custom CSS for better aesthetics
st.markdown(
    """
    <style>
    .stApp {
        background-color: #0e1117;
        color: #fafafa;
    }
    .stChatInputContainer {
        padding-bottom: 20px;
    }
    .stChatMessage {
        background-color: #262730;
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 10px;
    }
    .stSidebar {
        background-color: #262730;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_inngest_client() -> inngest.Inngest:
    return inngest.Inngest(app_id="rag_app", is_production=False)


def save_uploaded_pdf(file) -> Path:
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.name
    file_bytes = file.getbuffer()
    file_path.write_bytes(file_bytes)
    return file_path


async def send_rag_ingest_event(pdf_path: Path) -> None:
    client = get_inngest_client()
    await client.send(
        inngest.Event(
            name="rag/ingest_pdf",
            data={
                "pdf_path": str(pdf_path.resolve()),
                "source_id": pdf_path.name,
            },
        )
    )


async def send_rag_query_event(question: str, top_k: int) -> dict:
    client = get_inngest_client()
    result = await client.send(
        inngest.Event(
            name="rag/query_pdf_ai",
            data={
                "question": question,
                "top_k": top_k,
            },
        )
    )
    return result[0]


def _inngest_api_base() -> str:
    return os.getenv("INNGEST_API_BASE", "http://127.0.0.1:8288/v1")


def fetch_runs(event_id: str) -> list[dict]:
    url = f"{_inngest_api_base()}/events/{event_id}/runs"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        st.error(f"Error fetching runs: {e}")
        return []


def wait_for_run_output(
    event_id: str, timeout_s: float = 120.0, poll_interval_s: float = 0.5
) -> dict:
    start = time.time()
    last_status = None
    while True:
        runs = fetch_runs(event_id)
        if runs:
            run = runs[0]
            status = run.get("status")
            last_status = status or last_status
            if status in ("Completed", "Succeeded", "Success", "Finished"):
                return run.get("output") or {}
            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"Function run {status}")
        if time.time() - start > timeout_s:
            raise TimeoutError(
                f"Timed out waiting for run output (last status: {last_status})"
            )
        time.sleep(poll_interval_s)


# Sidebar for configuration and upload
with st.sidebar:
    st.title("Settings")
    st.caption("Upload your documents here")
    uploaded = st.file_uploader(
        "Choose a PDF", type=["pdf"], accept_multiple_files=False
    )
    if uploaded is not None:
        with st.spinner("Uploading and triggering ingestion..."):
            path = save_uploaded_pdf(uploaded)
            asyncio.run(send_rag_ingest_event(path))
            time.sleep(0.3)
        st.success(f"Ingested: {path.name}")

    st.divider()
    top_k = st.slider(
        "Retrieval Chunk Size (Top-K)", min_value=1, max_value=20, value=5
    )

# Main Chat Interface
st.title("📄 PDF Chat Assistant")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "sources" in message:
            with st.expander("View Sources"):
                for s in message["sources"]:
                    st.markdown(f"- {s}")

if prompt := st.chat_input("Ask a question about your PDF..."):
    # Add user message to state
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                event_id = asyncio.run(send_rag_query_event(prompt, int(top_k)))
                output = wait_for_run_output(event_id)
                answer = output.get("answer", "I couldn't generate an answer.")
                sources = output.get("sources", [])

                st.markdown(answer)
                if sources:
                    with st.expander("View Sources"):
                        for s in sources:
                            st.markdown(f"- {s}")

                # Add assistant response to state
                st.session_state.messages.append(
                    {"role": "assistant", "content": answer, "sources": sources}
                )

            except Exception as e:
                st.error(f"An error occurred: {e}")
