# Backend — RAG Pipeline

## Overview
The pipeline transforms uploaded documents into queryable knowledge and generates grounded answers.

## Stages

### REQ-BR-001: Document Loading
- Input: file path on disk.
- PDF: extract text via `PyMuPDF` (fitz). Preserve page numbers.
- TXT: read as UTF-8.
- Output: `list[DocumentPage]` where each item has `text` and `metadata` (filename, page number).

### REQ-BR-002: Chunking
- Strategy: recursive character splitting.
- Chunk size: 1000 characters.
- Chunk overlap: 200 characters.
- Each chunk inherits parent document metadata + gets a unique `chunk_id`.
- Library: `langchain.text_splitter.RecursiveCharacterTextSplitter`.

### REQ-BR-003: Embedding
- Model: `text-embedding-3-small` (OpenAI).
- Batch embed all chunks per document.
- Output: vectors stored alongside chunk text and metadata in ChromaDB.

### REQ-BR-004: Storage (ChromaDB)
- Single collection: `legal_documents`.
- Each record: `id` (chunk_id), `embedding`, `document` (chunk text), `metadata` (doc_id, doc_name, page).
- On document delete: remove all chunks matching `doc_id` from collection.

### REQ-BR-005: Retrieval
- Input: user question (string).
- Embed the question using same embedding model.
- Query ChromaDB: top-k=5 most similar chunks.
- Return chunks with metadata.

### REQ-BR-006: Generation
- Input: question, retrieved chunks, conversation history.
- System prompt:
  ```
  You are a legal assistant. Answer the user's question based ONLY on the
  provided context. If the context does not contain enough information,
  say so. Always cite which document and section your answer comes from.
  ```
- User prompt: question + context (chunk texts with source labels).
- Model: `gpt-4o`.
- Temperature: 0.1 (low creativity, high accuracy).
- Output: answer string + sources extracted from used chunks.

## Configuration (`core/config.py`)
| Variable              | Env Var                | Default                    |
|----------------------|------------------------|----------------------------|
| OpenAI API key       | `OPENAI_API_KEY`       | (required)                 |
| Embedding model      | `EMBEDDING_MODEL`      | `text-embedding-3-small`   |
| LLM model            | `LLM_MODEL`           | `gpt-4o`                   |
| Chunk size           | `CHUNK_SIZE`           | `1000`                     |
| Chunk overlap        | `CHUNK_OVERLAP`        | `200`                      |
| Retrieval top-k      | `RETRIEVAL_TOP_K`      | `5`                        |
| ChromaDB path        | `CHROMA_PERSIST_DIR`   | `./chroma_data`            |
| Upload directory     | `UPLOAD_DIR`           | `./uploads`                |
