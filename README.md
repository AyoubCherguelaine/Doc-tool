# DOCTool — Intelligent Document AI & Chat Workspace

A sophisticated RAG (Retrieval-Augmented Generation) system that lets you
**chat with PDF documents** using either a classic conversational chain or a
**free autonomous agent** that searches, reads specific pages, and
cross-references content using a ReAct loop.

**Powered by:** OpenAI GPT (LLM) + `text-embedding-3-small` (embeddings) +
FAISS (vector store) + PyMuPDF (page-level extraction) + **Hybrid RAG**
(BM25 keyword + dense embedding fusion via RRF) + optional GPT reranking.

---

## Docker

Run the full stack — PostgreSQL+pgvector, Redis, SeaweedFS, FastAPI backend and worker, and the Next.js frontend — with a single command:

```bash
cp .env-example .env      # add your OPENAI_API_KEY (and DB creds if you changed them)
docker compose up --build
```

| Service | URL | Notes |
| --- | --- | --- |
| Frontend | http://localhost:3000 | Next.js production server (Docker) |
| Backend API | http://localhost:8000/api | `/api/docs` for OpenAPI UI, `/api/health` for production probes |
| PostgreSQL (pgvector) | localhost:5436 | db `docuchat`, user `postgres`, password `docuchat123` |
| Redis (Queue & Cache) | localhost:6379 | Distributed task queue, rate limiting & token bucket |
| SeaweedFS (S3 Storage) | http://localhost:8333 | Private document bucket `docuchat-documents`; signed downloads |

Documents use **SeaweedFS**, a dedicated S3-compatible object storage service on `http://localhost:8333`, with bucket `docuchat-documents`. Its public `chrislusf/seaweedfs` image requires no Docker registry login and is pinned to the tested digest (SeaweedFS 4.50). The `seaweedfs_data` volume persists object data and metadata. Set `S3_ACCESS_KEY`, `S3_SECRET_KEY`, and `S3_BUCKET` in `.env`; these are application storage credentials, not registry credentials. Backend and worker use `http://seaweedfs:8333` internally. `S3_PUBLIC_ENDPOINT_URL` must be reachable by the browser because download links are signed directly for that endpoint. Storage failures are surfaced instead of writing objects to a local fallback.

To run the storage service without Docker, download the `weed` binary from the [SeaweedFS releases](https://github.com/seaweedfs/seaweedfs/releases) and run `AWS_ACCESS_KEY_ID=docuchat AWS_SECRET_ACCESS_KEY=docuchat-s3-development-secret S3_BUCKET=docuchat-documents weed mini -dir=./seaweed-data`. The Python app can connect using `S3_ENDPOINT_URL=http://localhost:8333`. Existing MinIO-only objects must be copied to the new bucket; the old volume is not deleted.

> The database schema (`backend/schema.sql`) is created automatically on first `docker compose up` (the data volume is empty). Subsequent starts reuse the persisted `db_data` volume; to reset, run `docker compose down -v`.

## Table of Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Project Structure](#project-structure)
4. [Installation](#installation)
5. [Configuration](#configuration)
 6. [Usage](#usage)
 7. [Agent Mode Explained](#agent-mode-explained)
 8. [Agent Modes](#agent-modes)
10. [Agent Modes](#agent-modes)
11. [Multi-Service Dashboard](#multi-service-dashboard)
12. [Hybrid RAG Explained](#hybrid-rag-explained)
13. [API Reference](#api-reference)
14. [Development](#development)
15. [License](#license)

---

## Features

| Feature | Description |
|---|---|
| **Multiple Specialized Agents** | Choose between `summary`, `research`, `extraction`, `comparison`, `factcheck`, `invoice`, `contract`, `google_ai`, `receipt`, `resume`, `compliance`, `form_parser`, `coordinator` modes, plus the classic `FreeAgent` |
| **Multi-Service Dashboard** | Dedicated `/services` page with enterprise Document AI service cards, category filters, and search |
| **Invoice & Receipt Processing** | Extract structured invoice and expense data (merchants, line items, totals, taxes, tips) as verified JSON |
| **Contract Analysis & Compliance** | Extract contract clauses/obligations, flag risks, and run automated PII/GDPR/HIPAA compliance audits |
| **Talent & Form Intelligence** | Screen resumes/CVs for skills and seniority; parse form key-values, checkboxes, and signatures |
| **Free Agent** | Autonomous ReAct-style agent that uses tools iteratively — search, read pages, summarize, compare — until it has a confident answer |
| **Page-Level Reading** | PyMuPDF-powered tools to read specific pages or page ranges ("special pages") |
| **Document Structure Extraction** | Extract document outlines (headings/bookmarks) and tables from PDFs |
| **Cheap OpenAI Embeddings** | `text-embedding-3-small` — the cheapest high-quality OpenAI embedding model |
| **Hybrid RAG (text + embedding)** | Combines BM25 keyword search + dense embeddings via Reciprocal Rank Fusion (RRF) |
| **Large Chunks** | 4 000-character chunks with 500-char overlap and semantic boundary detection |
| **Optional GPT Reranking** | Uses `gpt-6-luna` to re-rank top candidates for higher precision |
| **Perfect Text Extraction** | PyMuPDF with `sort=True` reading order, block extraction, and table detection |
| **Metadata Tracking** | Every chunk carries `doc_name`, `start_page`, `end_page`, and `chunk_index` |
| **Multi-Document** | Upload and query multiple PDFs simultaneously; compare across documents |
| **Dual Mode** | Switch between agent mode (iterative tool use) and conversational mode (classic Q&A) |
| **Multiple LLM Backends** | OpenAI GPT (default) or Ollama (local) |
| **Persistence** | Save and load FAISS indexes to disk |

---

## Architecture

### Overview

```
User Query
    │
    ▼
┌──────────────────────────────────────────────┐
│           Next.js Frontend (frontend/)             │
│           + FastAPI Backend (backend/)       │
│                                              │
│   Mode: [Summary Research Extract Compare Factcheck Coordinator] │
│   Backend: [OpenAI GPT]  Embedding: [text-   │
│   embedding-3-small]  Hybrid: [ON]            │
│   Auth: [Email + password]  DB: [PostgreSQL] │
└──────────────────────────────────────────────┘
    │                    │
    ▼                    ▼
┌──────────────┐    ┌──────────────────────┐
│  Multiple    │    │ ConversationChain    │
│  Specialized │    │ (gpt-6-luna)        │
│  Agents +    │    │                      │
│  FreeAgent   │    │                      │
│ (ReAct Loop) │    │                      │
└──────┬───────┘    └────────┬─────────────┘
       │                     │
       ▼                     ▼
┌───────────────────────────────────────────────┐
│   DocumentToolKit  │  SmartVectorStore       │
│                                        │
│  ┌─────────────┬───────────┬────────┬───┐ │
│  │ search_docs │ read_page │ summer-│   │ │
│  │             │ read_pages│  ize  │...│ │
│  └─────────────┴───────────┴────────┴───┘ │
│          │                              │
│          ▼                              │
│  ┌────────────────────────────────────┐ │
│  │  Hybrid RAG:                        │ │
│  │  ┌─────────────────────────────┐   │ │
│  │  │ Dense: OpenAI Embeddings   │   │ │
│  │  │ (text-embedding-3-small)    │   │ │
│  │  └─────────────────────────────┘   │ │
│  │  ┌─────────────────────────────┐   │ │
│  │  │ Sparse: BM25 Keyword Search │   │ │
│  │  └─────────────────────────────┘   │ │
│  │  ┌─────────────────────────────┐   │ │
│  │  │ Fusion: Reciprocal Rank     │   │ │
│  │  │ Fusion (RRF)                │   │ │
│  │  └─────────────────────────────┘   │ │
│  │  ┌─────────────────────────────┐   │ │
│  │  │ Re-rank: CrossEncoder       │   │ │
│  │  └─────────────────────────────┘   │ │
│  │  ┌─────────────────────────────┐   │ │
│  │  │ FAISS Vector Store           │   │ │
│  │  └─────────────────────────────┘   │ │
│  └────────────────────────────────────┘ │
└───────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│  documents/ module                           │
│  ┌──────────────┐   ┌──────────────┐         │
│  │ pdf_loader   │   │ splitter     │         │
│  │ (PyMuPDF     │   │ (LargeChunk  │         │
│  │  + tables)   │   │  + Semantic) │         │
│  └──────────────┘   └──────────────┘         │
└──────────────────────────────────────────────┘
```

### Data Flow

1. **PDF Upload** → `DocumentProcessor` loads PDFs via PyMuPDF with perfect
   text extraction, producing `PDFDocument` objects with per-page text
   and metadata.
2. **Chunking** → `SemanticChunkSplitter` splits pages into large (4 000-char)
   chunks, preserving page boundaries and detecting semantic section breaks.
3. **Embedding** → `SmartEmbedding` creates dense embeddings using OpenAI's
   `text-embedding-3-small` (cheap, 1,536-dim).
4. **Indexing** → `SmartVectorStore` builds FAISS (dense) + BM25 (sparse)
   indexes with rich metadata.
5. **Hybrid Retrieval** → When queried:
   - Dense vector search (FAISS) finds semantically similar chunks
   - BM25 keyword search finds textually matching chunks
   - RRF fusion combines both result lists
    - Optional GPT reranker re-scores final candidates
6. **Agent Loop** → The `FreeAgent` iteratively uses `DocumentToolKit` tools
   (search, read_page, summarize, compare) to build confidence before answering.

---

## Project Structure

```
Caht-With-Document-PDF/
├── backend/                       # FastAPI backend (auth, drive, chat API)
│   ├── server.py                  # FastAPI app — REST + streaming SSE endpoints
│   ├── auth.py                    # bcrypt + JWT auth helpers + dependency
│   ├── db.py                      # PostgreSQL connection pool + helpers
│   ├── rag.py                     # Document processing + RAG orchestration
│   ├── config.py                  # Pydantic-style env config
│   ├── .env                       # Backend env (DB url, JWT secret)
│   └── uploads/                   # Uploaded PDFs (gitignored)
│   └── faiss_indexes/             # FAISS indices on disk (gitignored)
├── frontend/                           # Next.js 15 frontend (TypeScript + Tailwind)
│   ├── src/app/                   
│   │   ├── login/                 # Login / signup
│   │   ├── (protected)/
│   │   │   ├── drive/             # Drive: upload + list documents + session picker
│   │   │   └── chat/[sessionId]/  # Streaming RAG chat
│   │   └── layout.tsx
│   ├── src/components/            # UI primitives + drive/chat components
│   ├── src/lib/                   # API client + shared types
│   ├── src/styles/globals.css
│   ├── .env.local                 # Frontend env (API url)
│   └── tests/e2e.spec.ts          # Playwright end-to-end test
├── documents/                     # PDF loading & chunking (page-aware)
│   ├── __init__.py
│   ├── pdf_loader.py              # PyMuPDF loader with page-level metadata
│   │                             # + table extraction + sorted text
│   ├── splitter.py                # LargeChunkSplitter + SemanticChunkSplitter
│   └── processors.py              # DocumentProcessor pipeline
├── embeddings/                    # Smart embedding & vector store (OpenAI)
│   ├── __init__.py
│   ├── smart_embedding.py         # OpenAI embeddings + RRF hybrid + reranker
│   ├── vectoreStore.py            # SmartVectorStore (FAISS + BM25 wrapper)
│   └── huggingfaceEmbedding.py    # Backwards-compatible factory (OpenAI)
├── chat/                          # Conversation chains (GPT-based)
│   ├── __init__.py
│   └── chatWithVSDB.py            # ConversationChain + factory functions
├── agent/                         # Free autonomous agent
│   ├── __init__.py
│   ├── agent.py                   # FreeAgent (ReAct loop)
│   ├── prompts.py                 # ReAct prompt + output parser
│   └── tools/
│       ├── __init__.py
│       ├── registry.py            # Tool dataclass + ToolRegistry
│       └── document_tools.py      # search, read_page, summarize, etc.
├── tests/                         # Unit tests (91 tests)
│   ├── __init__.py
│   ├── test_pdf_loader.py
│   ├── test_splitter.py
│   ├── test_smart_embedding.py
│   └── test_agent.py
├── .env                           # Root env (OpenAI API key + model)
├── .env-example
├── requirements.txt               # Python dependencies
├── ruff.toml                      # Ruff configuration
├── mypy.ini                       # Mypy configuration
└── README.md                      # This file
```

---

## Installation

### Prerequisites

- Python 3.10+
- Node.js 18+
- Docker (to run the PostgreSQL+pgvector container, or use any Postgres)
- An [OpenAI API key](https://platform.openai.com/api-keys) (for GPT LLM + embeddings)

### Step 1 — Clone & Create Virtual Environment

```bash
git clone <repo-url>
cd Caht-With-Document-PDF
python -m venv venv
source venv/bin/activate     # Linux/macOS
# venv\Scripts\activate      # Windows
```

### Step 2 — Install Python Dependencies (backend)

```bash
pip install -r requirements.txt
```

### Step 3 — Start PostgreSQL + create the schema

```bash
docker run -d --name docuchat_pg \
  -e POSTGRES_PASSWORD=docuchat123 -e POSTGRES_DB=docuchat \
  -p 5436:5432 pgvector/pgvector:pg16

PGPASSWORD=docuchat123 psql -h 127.0.0.1 -p 5436 -U postgres -d docuchat \
  -f backend/schema.sql
```

### Step 4 — Configure Environment

Create the root `.env` (OpenAI key) and `backend/.env` (database):

```env
# .env  (repository root)
OPENAI_API_KEY=sk-...
DEFAULT_MODEL=gpt-6-luna
```

```env
# backend/.env
DATABASE_URL=postgresql://postgres:docuchat123@localhost:5436/docuchat
JWT_SECRET=docuchat-dev-secret-change-me
```

### Step 5 — Install Frontend Dependencies

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=/api" > .env.local
```

---

## Configuration

### Environment Variables

| Variable | Where | Required | Default | Description |
|---|---|---|---|---|
| `OPENAI_API_KEY` | root `.env` | Yes | — | OpenAI key for GPT + `text-embedding-3-small` |
| `DEFAULT_MODEL` | root `.env` | No | `gpt-6-luna` | LLM used for generation. Note: `gpt-6-luna` only supports `temperature=1`, so the agent/conversation chain leave temperature unset. |
| `EMBEDDING_MODEL` | root `.env` | No | `text-embedding-3-small` | Embedding model (1 536-dim) |
| `DATABASE_URL` | `backend/.env` | Yes | `postgresql://postgres:docuchat123@localhost:5436/docuchat` | PostgreSQL (with the `pgvector` extension) |
| `JWT_SECRET` | `backend/.env` | No | `docuchat-dev-secret-change-me` | HS256 secret for auth tokens |
| `NEXT_PUBLIC_API_URL` | `frontend/.env.local` | No | `/api` | API base URL seen by the browser; same origin by default |
| `BACKEND_URL` | `frontend/.env.local` or Docker build argument | No | `http://127.0.0.1:8000` (Docker: `http://backend:8000`) | Server-side API proxy target; rebuild frontend after changing |
| `OLLAMA_HOST` | root `.env` | No | — | Ollama server URL (optional LLM fallback) |

> **Backend `.env` setup:** copy `backend/.env` (already populated with dev defaults), then set `DATABASE_URL` / `JWT_SECRET` as needed.

### One-command start (Docker PostgreSQL)

A dedicated Postgres+pgvector container is used for users, documents, chunks,
sessions and messages:

```bash
docker run -d --name docuchat_pg \
  -e POSTGRES_PASSWORD=docuchat123 -e POSTGRES_DB=docuchat \
  -p 5436:5432 pgvector/pgvector:pg16
```

Then create the schema (run once):

```bash
PGPASSWORD=docuchat123 psql -h 127.0.0.1 -p 5436 -U postgres -d docuchat \
  -f backend/schema.sql
```

### Embedding Configuration

The default `SmartEmbeddingConfig` uses:

- **Embedding model**: `text-embedding-3-small` (cheapest OpenAI model, 1,536-dim)
- **Optional GPT reranker**: `gpt-6-luna` for relevance re-scoring (opt-in)
- **Chunk size**: 4 000 characters (vs. original 1 028)
- **Chunk overlap**: 500 characters
- **Hybrid search**: ON by default (BM25 + dense RRF fusion)

To customize:

```python
from embeddings.smart_embedding import SmartEmbedding, SmartEmbeddingConfig

config = SmartEmbeddingConfig(
    embedding_model="text-embedding-3-large",  # more powerful, more expensive
    use_hybrid=True,
    hybrid_alpha=0.5,  # equal weight dense + sparse
    use_rrf=True,
    use_reranker=False,  # disable GPT reranker for cost savings
)
embedding = SmartEmbedding(config)
```

### LLM Configuration

Default: `gpt-6-luna` (cheap + good). For higher quality: `gpt-4o` or `gpt-4-turbo`.

```python
from chat.chatWithVSDB import get_llm

llm = get_llm(model_name="gpt-4o", temperature=0.2)
```

---

## Usage

Run the **backend (FastAPI)** and the **frontend (Next.js)** together. They
communicate over HTTP; the OpenAI key lives only on the backend.

### 1. Start the backend (FastAPI)

```bash
# from the project root, with the venv active
source venv/bin/activate
uvicorn backend.server:app --host 0.0.0.0 --port 8000 --reload
```

API docs: <http://localhost:8000/docs>.

### 2. Start the frontend (Next.js)

```bash
# in a separate terminal
cd frontend
npm install      # first time only
npm run dev      # -> http://localhost:3000
```

### 3. Use the app

1. Open <http://localhost:3000> — explore the landing page, then register or sign in (email + password).
2. **Drive** — click **"Upload document"**, pick a PDF, then **"Upload & process"**.
   The file is extracted, chunked, embedded and indexed (FAISS on disk, chunk
   text persisted in PostgreSQL).
3. Click **"Chat"** on a document → choose **"New conversation"** or pick an
   existing session (sessions are recalled from PostgreSQL).
   4. Ask a question. Responses **stream** token-by-token. Switch the mode toggle:
      - **Conversational** — classic retrieval chain.
      - **Agent** — the free ReAct agent that searches, reads specific pages, and
        cross-references before answering.
      - **Summary** / **Research** / **Extraction** / **Comparison** / **Fact Check** /
        **Coordinator** — specialized agents for specific tasks.

Sessions, messages and documents are stored in PostgreSQL, so your history
survives restarts.

### Backend API overview

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/api/auth/register` | Create account → returns `accessToken` |
| `POST` | `/api/auth/login` | Login → returns `accessToken` |
| `GET`  | `/api/auth/me` | Current user (Bearer auth) |
| `GET`  | `/api/documents` | List the user's documents |
| `POST` | `/api/documents/upload` | Upload + process a PDF (multipart) |
| `GET`  | `/api/documents/{id}/sessions` | List a document's sessions |
| `POST` | `/api/sessions` | Create a session for a document |
| `GET`  | `/api/sessions/{id}` | Load a session + message history |
| `DELETE` | `/api/sessions/{id}` | Delete a session |
| `POST` | `/api/sessions/{id}/chat` | Streaming chat (SSE, JSON body `{message, mode}`) |
| `GET`  | `/api/documents/{doc_id}/outline` | Document structural outline (headings) |
| `GET`  | `/api/capabilities/agents` | List available agent modes and their capabilities |
| `POST` | `/api/documents/{doc_id}/workflow` | Execute a named workflow (summary, research, comparison, etc.) |

> All routes except `/api/health` require `Authorization: Bearer <accessToken>`.

### Option 2: Python API (backend building blocks)

These modules are reused **as-is** by the FastAPI backend.

#### Document Processing

```python
from documents.processors import DocumentProcessor, ProcessingConfig
from documents.pdf_loader import load_pdfs

# Load PDFs with perfect text extraction + page metadata
documents = load_pdfs(["report.pdf", "manual.pdf"])

# Split into large, metadata-rich chunks
processor = DocumentProcessor(ProcessingConfig(
    use_semantic_split=True,
    chunk_size=4000,
    chunk_overlap=500,
))
chunks = processor.process_documents(documents)
```

#### Smart Embedding + Hybrid Vector Store

```python
from embeddings.smart_embedding import SmartEmbedding, SmartEmbeddingConfig
from embeddings.vectoreStore import SmartVectorStore

embedding = SmartEmbedding(SmartEmbeddingConfig(
    embedding_model="text-embedding-3-small",
    use_hybrid=True,       # BM25 + dense
    use_rrf=True,          # Reciprocal Rank Fusion
    use_reranker=True,     # GPT rerank (extra cost)
))
vs = SmartVectorStore(embedding=embedding).build(chunks)

# Hybrid search: combines keyword + embedding + RRF + rerank
results = vs.search("What are the key findings?", top_k=5)
for doc in results:
    print(f"[p. {doc.metadata['start_page']}] {doc.page_content[:200]}")

# Save for later
vs.save("my_index")
```

#### Free Agent

```python
from langchain_openai import ChatOpenAI
from agent.agent import FreeAgent, AgentConfig
from agent.tools.document_tools import DocumentToolKit

llm = ChatOpenAI(model="gpt-6-luna", temperature=0.3)

tool_kit = DocumentToolKit(
    vector_store=vs,
    documents=documents,
    llm=llm,
)

agent = FreeAgent(
    llm=llm,
    tool_kit=tool_kit,
    config=AgentConfig(max_iterations=8, verbose=True),
)

result = agent.run("Compare the methodology sections across all documents.")

print(result.response)      # The final answer
print(len(result.steps))    # How many tool calls were made
print(result.success)       # Whether it reached a FINAL action
```

#### Conversational Chain

```python
from chat.chatWithVSDB import get_conversation_chain

chain = get_conversation_chain(vs, model_name="gpt-6-luna")

response = chain({"question": "What is the conclusion?"})
print(response["answer"])
```

---

## Agent Mode Explained

The **FreeAgent** implements a ReAct loop. Each iteration:

1. **Think** — The LLM reasons about the question and decides what to do.
2. **Act** — The LLM selects a tool and provides parameters.
3. **Observe** — The tool result is fed back to the LLM.
4. **Repeat** — Steps 1–3 until the agent is confident enough to answer.

### Available Tools

| Tool | Description | Parameters |
|---|---|---|
| `search_documents` | Hybrid search (BM25 + dense + RRF + rerank) | `query`, `top_k` |
| `read_page` | Read a specific page | `doc_name`, `page_num` |
| `read_pages` | Read a page range | `doc_name`, `start_page`, `end_page` |
| `list_documents` | List loaded PDFs | _(none)_ |
| `summarize` | Summarize text | `text` |
| `compare_documents` | Search across all documents | `query`, `top_k_per_doc` |
| `get_metadata` | Get chunk/page metadata | `doc_name`, `page_num` |

## Agent Modes

The system supports multiple specialized agent modes. Each mode uses a different
agent class with tailored system prompts and tool configurations.

| Mode | Agent | Description |
|---|---|---|
| `conversational` | *(none)* | Classic Q&A with conversational memory (no agent loop) |
| `agent` | `FreeAgent` | General-purpose ReAct agent with full tool access |
| `summary` | `SummaryAgent` | Generate an executive summary of the documents |
| `research` | `ResearchAgent` | Deep research — gather evidence and cite sources |
| `extraction` | `ExtractionAgent` | Extract structured data, tables, and specific facts |
| `comparison` | `ComparisonAgent` | Compare and contrast across multiple documents |
| `factcheck` | `FactCheckAgent` | Verify claims against document content |
| `invoice` | `InvoiceAgent` | Extract structured invoice data as JSON |
| `contract` | `ContractAgent` | Analyze contracts — clauses, risks, obligations |
| `google_ai` | `GoogleAIDocumentAgent` | Multimodal document intelligence, layout parsing, and entity extraction |
| `receipt` | `ReceiptAgent` | Itemized receipts, taxes, tips, payment methods, and financial verification |
| `resume` | `ResumeAgent` | Candidate profiling, skills taxonomy, work history, and seniority assessment |
| `compliance` | `ComplianceAgent` | PII detection, sensitive credential leaks, and GDPR/HIPAA risk scoring |
| `form_parser` | `FormParserAgent` | Form fields, key-value mappings, checkbox states, and signature blocks |
| `coordinator` | `CoordinatorAgent` | Route questions to the most appropriate sub-agent |

### Agent Trace Example

```
Iteration 1
  Thought: The user asks about methodology differences. I should search first.
  Action:  search_documents
  Params:  {"query": "methodology approach", "top_k": 5}
  Observation: Found results in report.pdf (pages 3-4) and manual.pdf (page 7)...

Iteration 2
  Thought: I need to see the exact text on page 3 of report.pdf.
  Action:  read_page
  Params:  {"doc_name": "report.pdf", "page_num": 3}
  Observation: "Our methodology uses a mixed-methods approach..."

Iteration 3
  Thought: Now let me read the corresponding section in manual.pdf.
  Action:  read_pages
  Params:  {"doc_name": "manual.pdf", "start_page": 7, "end_page": 9}
  Observation: "The manual describes a purely quantitative approach..."

Iteration 4
  Thought: I have enough information to compare.
  Action:  FINAL
  Response: The key difference is that report.pdf uses a mixed-methods
            approach (p. 3), while manual.pdf exclusively uses quantitative
            methods (p. 7-9)...
```

---

## Hybrid RAG Explained

The system uses **three complementary retrieval strategies** fused together:

### 1. Dense Retrieval (FAISS)
- Embeds the query with `text-embedding-3-small`
- Finds the top-k most semantically similar chunks via vector similarity
- **Strengths**: Captures semantic meaning, handles synonyms/paraphrasing
- **Weaknesses**: May miss exact term matches, embedding quality limits recall

### 2. Sparse Retrieval (BM25)
- Keyword-based search over chunk text
- Uses traditional TF-IDF + BM25 scoring
- **Strengths**: Exact term matching, good for names/dates/numbers
- **Weaknesses**: Misses semantically related but lexically different text

### 3. Fusion (RRF)
- **Reciprocal Rank Fusion** combines both result lists
- RRF score = `sum(1 / (rank + k))` for each list the doc appears in
- No hyperparameter tuning needed — works well with default `k=60`
- **Strengths**: Robust to individual retrieval method failures

### 4. Optional Cross-Encoder Reranking
- After fusion, top candidates are re-ranked with `gpt-6-luna` for relevance scoring
- Cross-encoders compare query+text jointly for higher precision
- **Strengths**: Best precision for final candidate ordering

```python
# Hybrid search pipeline:
# Query → [Dense FAISS] → top-20
#       → [BM25 sparse] → top-20
#       → [RRF fusion]  → merged + ranked
#       → [CrossEncoder] → final top-k
```

---

## Multi-Service Dashboard

The `/services` page provides a dashboard of document-processing services.
Each service is a specialized agent preset that processes documents in a
purpose-built way:

| Service | Mode | Output |
|---|---|---|
| **Document Chat** | `conversational` | Conversational Q&A |
| **Invoice Processing** | `invoice` | Structured invoice JSON (line items, totals, taxes) |
| **Receipt & Expenses** | `receipt` | Itemized receipts, tips, taxes, and expense categories |
| **Contract Analysis** | `contract` | Clause extraction, risk flags, key dates |
| **PII & Compliance Audit** | `compliance` | Privacy risk score (0-100), PII enumeration, and redaction preview |
| **Resume & Talent** | `resume` | Skills matrix, work history, and seniority assessment |
| **Intelligent Form Parser** | `form_parser` | Form fields, checkboxes [X], and signature states |
| **Executive Summary** | `summary` | Markdown executive summary |
| **Deep Research** | `research` | Evidence-based research brief with citations |
| **Data Extraction** | `extraction` | Markdown tables of key metrics and figures |
| **Google AI Document** | `google_ai` | Multimodal document intelligence, layout parsing, and entity extraction |

To use a service: open `/services`, choose a source document, and click
the service card. The chat interface loads with the corresponding mode pre-selected.

---

## Company API Usage & Credit Billing

Every company account receives **300 free trial credits** upon creation (free trial tier available only, zero credit card required).
Each Document AI service is priced dynamically according to the underlying LLM token, vision, and reasoning compute intensity.

### Service Credit Pricing

| Document AI Service | API Route | LLM Compute Tier | Cost (Credits) | Free Trial Capacity |
|---|---|---|---|---|
| **Document Chat** | `/api/v1/services/chat` | Light | 5 credits | ~60 calls |
| **Executive Summary** | `/api/v1/services/summary` | Light-Moderate | 10 credits | ~30 calls |
| **Data Extraction** | `/api/v1/services/extraction` | Moderate | 15 credits | ~20 calls |
| **Intelligent Form Parser** | `/api/v1/services/form_parser` | Moderate | 20 credits | ~15 calls |
| **Receipt & Expenses** | `/api/v1/services/receipt` | Moderate | 20 credits | ~15 calls |
| **Invoice Processing** | `/api/v1/services/invoice` | Moderate-Heavy | 25 credits | ~12 calls |
| **Resume & Talent** | `/api/v1/services/resume` | Moderate-Heavy | 25 credits | ~12 calls |
| **PII & Compliance Audit** | `/api/v1/services/compliance` | Heavy | 30 credits | ~10 calls |
| **Contract Analysis** | `/api/v1/services/contract` | Heavy | 35 credits | ~8 calls |
| **Google AI Multimodal** | `/api/v1/services/google_ai` | Multimodal Heavy | 40 credits | ~7 calls |
| **Auto-Routing Coordinator** | `/api/v1/services/coordinator` | Multi-Agent | 45 credits | ~6 calls |
| **Deep Research** | `/api/v1/services/research` | Multi-Step ReAct | 50 credits | ~6 calls |

### Authenticating Company API Calls

Pass your live key in either the `X-API-Key` or `Authorization` header:

```bash
curl -X POST "http://localhost:8000/api/v1/services/invoice" \
  -H "X-API-Key: docu_live_your_company_key_here" \
  -H "Content-Type: application/json" \
  -d '{"document_id": "YOUR_DOCUMENT_UUID"}'
```

Every response returns headers:
* `X-Credits-Cost: 25`
* `X-Credits-Remaining: 1175`
* `X-Trial-Plan: free_trial`

If credits are exhausted, the endpoint returns `402 Payment Required`. Manage keys, inspect live quotas, and review consumption history at `/usage`.

---

## API Reference

### `documents/`

| Module | Key Classes/Functions |
|---|---|
| `pdf_loader` | `load_pdf()`, `load_pdfs()`, `extract_page_text()`, `PDFDocument`, `PageText` |
| `splitter` | `LargeChunkSplitter`, `SemanticChunkSplitter`, `split_documents()` |
| `processors` | `DocumentProcessor`, `ProcessingConfig` |
| `structure` | `extract_outline()`, `extract_tables()`, `Heading`, `TableExtract` |

### `embeddings/`

| Module | Key Classes/Functions |
|---|---|
| `smart_embedding` | `SmartEmbedding`, `SmartEmbeddingConfig` (OpenAI + RRF hybrid) |
| `vectoreStore` | `SmartVectorStore`, `VectorStoreConfig` |
| `huggingfaceEmbedding` | `get_vectore_db()`, `get_embedding_model()` |

### `chat/`

| Module | Key Classes/Functions |
|---|---|
| `chatWithVSDB` | `ConversationChain`, `get_conversation_chain()`, `get_llm()` |

### `agent/`

| Module | Key Classes/Functions |
|---|---|
| `agent` | `FreeAgent`, `AgentConfig`, `AgentResult` |
| `agents.base` | `BaseAgent`, `BaseAgentConfig`, `AgentResult` |
| `agents.summary` | `SummaryAgent` — executive summaries |
| `agents.research` | `ResearchAgent` — deep research with evidence gathering |
| `agents.extraction` | `ExtractionAgent` — structured data extraction |
| `agents.comparison` | `ComparisonAgent` — multi-document comparison |
| `agents.factcheck` | `FactCheckAgent` — claim verification |
| `agents.invoice` | `InvoiceAgent` — invoice data extraction as JSON |
| `agents.contract` | `ContractAgent` — contract analysis and risk flagging |
| `agents.coordinator` | `CoordinatorAgent` — routes questions to sub-agents |
| `tools.registry` | `Tool`, `ToolRegistry` |
| `tools.document_tools` | `DocumentToolKit` (7 tools) |
| `tools.enhanced` | `EnhancedDocumentKit` — extract_table, verify_fact, calculate, get_outline, extract_invoice_data, extract_contract_data, ocr_read_page, ocr_extract_invoice, ocr_extract_contract |
| `tools.ocr` | `OcrService`, `PdfRenderer` — vision-based OCR from scanned PDFs |
| `prompts` | `SYSTEM_PROMPT`, `REACT_PROMPT`, `parse_agent_output()` |

---

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Adding a New Tool

1. Add a method to `DocumentToolKit` in `agent/tools/document_tools.py`
2. Register it in `DocumentToolKit.register_all()`
3. Add tests in `tests/test_agent.py`

```python
# In DocumentToolKit
def my_tool(self, param: str) -> str:
    """Description of what this tool does."""
    result = ...  # your logic
    return str(result)

# In register_all()
registry.register(
    Tool(
        name="my_tool",
        description="...",
        parameters={"type": "object", "properties": {"param": {"type": "string"}}, "required": ["param"]},
        func=self.my_tool,
    )
)
```

### Linting

```bash
ruff check .
ruff format .
mypy .
```

### Key Design Decisions

1. **PyMuPDF over PyPDF2** — Better text extraction quality, native page-level
   access, table detection, and `sort=True` for correct reading order.
2. **4 000-char chunks** — Large enough to preserve document context, small
   enough for effective retrieval. Semantic splitting ensures chunks break at
   logical section boundaries.
3. **OpenAI `text-embedding-3-small`** — Cheapest high-quality embedding model.
   1,536-dim with excellent retrieval performance.
4. **Hybrid RAG with RRF** — Combines the strengths of dense (semantic) and
   sparse (keyword) retrieval. RRF is parameter-free and robust.
5. **gpt-6-luna** — Cost-effective LLM with strong reasoning for the agent loop.
6. **Custom ReAct loop** — Full control over the agent's reasoning process,
   rather than relying on opaque LangChain abstractions.

---

## License

This project is provided as-is for educational and research purposes.

---

*Powered by OpenAI • FAISS • PyMuPDF • Hybrid RAG (BM25 + text-embedding-3-small) • Cross-Encoder Reranking*

## Product workspace update

The public `/` route is now a landing page. Sign in or create an account at `/login` to use:

- `/drive`: workspace overview with live document, conversation, page/section, and storage counts; recent chats; AI shortcuts; document search, type filters, sorting, and grid/list views.
- `/drive?view=documents`: document library.
- `/conversations`: searchable conversation history.
- `/agents`: AI studio with executive summary, research, data extraction, and action-item workflows. Selecting a workflow prepares an editable prompt in a new conversation; it does not send automatically.
- `/chat/[sessionId]`: streamed document chat or research agent, configurable answer length and enabled model, a source text reader, response copying, and Markdown export. Stop cancels the browser request; an already-running provider/tool call may still complete on the server.

### Supported files

Upload PDF, Word **DOCX**, Excel **XLSX / XLS**, CSV, TXT, or Markdown files up to **5 MB and 3 pages** across all services, including Advanced OCR and API uploads. PDFs use their actual page count; other formats use the extracted sections shown in the document reader. Documents over either limit are rejected. Word tables are included in document order. Excel worksheet names and original row numbers are preserved; large sheets use sections of 150 nonempty rows. Formula text is retained in XLSX and is **not executed or recalculated**. Old binary Word `.doc` files must be saved as `.docx` first. Scanned PDF images need OCR before upload; image OCR is not included.

PDF citations refer to physical pages. Word/text citations refer to logical text sections, and spreadsheet citations refer to worksheet sections, not printed pages. The source panel displays extracted text rather than a visual Office/PDF renderer. The research agent searches and reads the selected document; it does not browse the web.

### Model configuration and persistence

`DEFAULT_MODEL` is always available in the chat model selector. Set `CHAT_MODELS` to a comma-separated list of additional model IDs supported by your configured provider. The server validates model choices. Existing OpenAI-compatible provider configuration remains in use. Restart the backend after changing these values.

```bash
# Install updated parsing dependencies locally
venv/bin/pip install -r requirements.txt
cd frontend
npm ci
```

For Docker, rebuild with `docker compose up -d --build`. Uploaded sources and index directories now use named volumes so newly uploaded files survive backend container recreation. If an earlier container already holds uploads in its writable layer, copy those files out before recreating it and restore them into the upload volume; database metadata alone cannot restore original file contents.

### Verification

```bash
venv/bin/pytest -q
venv/bin/ruff check backend tests
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

Loader regression tests cover Word paragraph/table order, worksheet names and row numbering, formulas and zero values, CSV quoting, Unicode text, PDF routing, and empty/unsupported files. API tests cover model/mode validation, source ownership, scoped conversation listing, upload limits, message-history ordering, streamed answer persistence, and cleanup after a failed parse.

---

## B2B SaaS Pipeline Integration & Model Context Protocol (MCP)

DocuChat provides an enterprise-ready B2B platform with dedicated developer APIs, background webhook automation, a Python SDK, and full Anthropic **Model Context Protocol (MCP)** support for **Claude Code**, **Claude Desktop / Claude Chat**, and **GPT Chats**.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        AI CLIENTS & PIPELINES                          │
│                                                                        │
│   Claude Code CLI    Claude Desktop      ChatGPT / GPT-4o    Airflow   │
│   (stdio transport)   (stdio / SSE)       (OpenAPI / Tools)  (Python)  │
└──────────┬──────────────────┬────────────────────┬───────────────┬─────┘
           │                  │                    │               │
           ▼                  ▼                    ▼               ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        DOCUCHAT B2B BACKEND                            │
│                                                                        │
│  • Model Context Protocol (MCP 2.x Server)  [/mcp/sse, stdio]          │
│  • B2B REST Pipeline API v1                [/api/v1/pipeline/run]      │
│  • ChatGPT Custom GPT Actions Schema       [/api/v1/gpt/openapi.json]  │
│  • OpenAI Function Calling Catalog         [/api/v1/openai/tools]      │
│  • Atomic Credit Billing & Usage Logs      [300 Trial Credits]         │
└────────────────────────────────────────────────────────────────────────┘
```

---

### 1. Model Context Protocol (MCP)

The built-in MCP server exposes DocuChat's document intelligence directly to AI coding tools and desktop assistants.

#### Registered MCP Tools:
- `docuchat_list_documents(limit)`: List documents in company workspace.
- `docuchat_upload_document(file_path, content, filename)`: Ingest and index local file or raw text.
- `docuchat_search_chunks(query, document_id, top_k)`: Hybrid vector + BM25 keyword search with citations.
- `docuchat_query_document(document_id, question)`: Grounded RAG Q&A.
- `docuchat_extract_invoice(document_id, query)`: Structured invoice line items, tax, and totals JSON.
- `docuchat_analyze_contract(document_id, query)`: Contract liabilities, indemnities, and termination terms.
- `docuchat_audit_compliance(document_id, query)`: PII detection, GDPR/HIPAA risk score, redactions.
- `docuchat_parse_form(document_id, query)`: Extract form fields, checkboxes `[X]`, and tables.
- `docuchat_summarize_document(document_id, query)`: Executive summary with key findings.
- `docuchat_compare_documents(document_id_a, document_id_b)`: Cross-document discrepancy analysis.
- `docuchat_get_company_credits()`: Check real-time credit balance and pricing.

#### Connect to Local Claude Code (CLI):
```bash
# Register DocuChat MCP server with Claude Code
claude mcp add docuchat -- python3 -m backend.mcp.server

# Start Claude Code and query your documents
claude
> "Upload /path/to/invoice.pdf to DocuChat and extract all line items into a table."
```

#### Connect to Claude Desktop (Claude Chat):
Add this block to your `claude_desktop_config.json`:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "docuchat": {
      "command": "python3",
      "args": [
        "-m",
        "backend.mcp.server"
      ],
      "env": {
        "DOCUCHAT_API_KEY": "docu_live_your_company_api_key",
        "DOCUCHAT_BASE_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

#### Connect via Server-Sent Events (SSE):
The FastAPI server automatically mounts the MCP SSE transport at:
- SSE stream: `http://127.0.0.1:8000/mcp/sse`
- Message endpoint: `http://127.0.0.1:8000/mcp/messages`

---

### 2. Integration with GPT Chats & ChatGPT Actions

#### ChatGPT Custom GPTs (Actions):
1. In ChatGPT, navigate to **Create a GPT** -> **Configure** -> **Actions** -> **Create new action**.
2. Click **Import from URL** and enter:
   `http://127.0.0.1:8000/api/v1/gpt/openapi.json`
3. Under **Authentication**, select **API Key**, type **Bearer**, and paste your `docu_live_...` API key.
4. Your Custom GPT now has direct access to upload, search, invoice, contract, and RAG tools!

#### OpenAI Function Calling (Python / LangChain / GPT-4o):
Fetch ready-to-use tool schemas directly:
```python
import httpx
from openai import OpenAI

openai_client = OpenAI()
tools = httpx.get("http://127.0.0.1:8000/api/v1/openai/tools").json()["tools"]

response = openai_client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Extract invoice items from doc-9812"}],
    tools=tools,
)
```

---

### 3. B2B Pipeline REST API & Python SDK

Automate document processing inside Apache Airflow, Prefect, Celery, or GitHub Actions.

#### Python Pipeline SDK (`DocuChatClient`):
```python
from backend.sdk import DocuChatClient

client = DocuChatClient(
    api_key="docu_live_your_key",
    base_url="http://127.0.0.1:8000"
)

# 1. Ingest document into pipeline
doc = client.upload_document("invoices/october_batch.pdf")
doc_id = doc["documentId"]

# 2. Extract structured invoice JSON
result = client.extract_invoice(doc_id)
print("Vendor:", result["data"]["vendor"])
print("Total:", result["data"]["total"])
print("Credits Remaining:", result["creditsRemaining"])

# 3. Hybrid search across document chunks
matches = client.search(doc_id, query="Payment terms and late fees", top_k=3)
```

#### Core Pipeline Endpoints:
| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/api/v1/documents/upload` | Ingest multipart file or JSON text content, returns `documentId`. |
| `GET` | `/api/v1/documents` | List company documents with pagination (`limit`, `offset`). |
| `GET` | `/api/v1/documents/{id}` | Inspect document status, size, and page breakdown. |
| `GET` | `/api/v1/documents/{id}/search` | Semantic embedding + BM25 keyword search with citations. |
| `POST` | `/api/v1/ocr/advanced` | Vision-based semantic page blocks with flexible content, coordinates, and continuation links. |
| `POST` | `/api/v1/pipeline/run` | Execute specialized AI agent (`invoice`, `contract`, `compliance`, `summary`, `form_parser`) with automated credit deduction and refund on error. Supports `webhook_url`. |
| `POST` | `/api/v1/pipeline/jobs` | Submit asynchronous background pipeline job to Redis worker queue (returns `202 Accepted` + `jobId`). |
| `GET` | `/api/v1/pipeline/jobs/{id}` | Poll background job progress (0-100) and structured output. |
| `GET` | `/api/v1/pipeline/jobs` | List recent background pipeline jobs. |
| `POST` | `/api/v1/pipeline/batch` | Execute batch multi-document workloads. |
| `GET` | `/api/v1/storage/status` | SeaweedFS S3 storage health, bucket, and endpoint. |
| `GET` | `/api/v1/storage/documents/{id}/presigned-url` | Generate an expiring signed document download URL. |
| `GET` | `/api/v1/gpt/openapi.json` | ChatGPT Custom GPT Actions OpenAPI 3.1 specification. |
| `GET` | `/api/v1/openai/tools` | OpenAI function calling schema array. |
| `GET` | `/api/v1/company/account` | Current trial credits (300 initial) and plan tier. |
| `GET` | `/api/v1/company/pricing` | Credit consumption rates per LLM tier. |

---

### Advanced OCR: semantic page blocks

Open **Advanced OCR** in the workspace navigation, select an uploaded PDF and
an inclusive page range (up to 50 pages), then extract and download JSON.
The API accepts either the normal Bearer session token or a company API key:

```http
POST /api/v1/ocr/advanced
Authorization: Bearer <token>
Content-Type: application/json

{"document_id":"<uploaded-pdf-id>","start_page":1,"end_page":3,"language":"auto"}
```

The original OCR block endpoints and agent tools now use this same semantic
engine by default, including PDFs with native text. Each block retains structured
`content` and includes a separate `ocr_text` containing the full transcription.
Pages and documents also include `ocr_text` assembled in reading order. Visual
descriptions stay separate from visible text. Existing `metadata`, `title`,
`table.content_md`, and `image` convenience fields remain available on the original
endpoints. Coordinates now consistently use the normalized 0–1000 canvas,
including `metadata.bbox`; clients previously expecting PDF points must adjust.
`force_ocr` remains accepted for compatibility, and both values use vision.
These endpoints therefore require a configured vision-capable model even for
native PDFs. The standalone native extraction helper remains available in Python.

This mode adapts `examy_ocr`'s semantic grouping, independent block count check,
and previous-page reference idea. It uses the configured default vision-capable
model on full rendered pages. It does not create image crops or use the old
project's exam/question schemas. `content` accepts any JSON value and additional
block fields are retained. `type`, `content`, `ocr_text`, and a normalized
`bbox: [left, top, right, bottom]` in the range 0–1000 are required from the model.
The service adds `id`, `page_number`, `reading_order`, and
`continues_previous_block`; continuations also include `previous_block_id`.

Pages are processed sequentially. Each receives only the last meaningful block
of the immediately preceding selected page, excluding headers, footers, and
side labels. The first selected page has no outside context. The response
contains both `pages` and a flattened `blocks` list. A malformed response or
block-count mismatch gets one retry; persistent extraction failures return 502,
and invalid ranges or unsupported document types return 422. The request is
synchronous, so clients and proxies need a timeout suitable for the page count.
As with the existing OCR inspection endpoints, this endpoint does not deduct
application credits; model provider usage still applies.

### 4. Bilingual (English & Arabic) Document Intelligence Suite

DocuChat includes specialized agents optimized specifically for Arabic & English enterprise pipelines, GCC/Saudi regulatory formats (ZATCA, Iqama, Saudi National IDs, GCC IBANs, Commercial Registrations):

| Service | Arabic Name | Description | Credits |
| --- | --- | --- | :---: |
| **`redaction`** | **حجب البيانات وتطهير الوثائق** | Automatically redacts PII in Arabic & English (Saudi National ID, Iqama, GCC IBANs `SA...`/`AE...`/`EG...`, Tax IDs, phones, emails). | **25** |
| **`classifier`** | **تصنيف وتوجيه المستندات** | Classifies incoming documents (Invoice, Contract, Financial Statement, Resume, CR, Government Letter) and outputs language (`ar`/`en`), urgency, and target routing department. | **15** |
| **`financial_statement`** | **تحليل القوائم المالية** | Extracts balance sheet and P&L metrics under IFRS & SOCPA (Revenue, EBIT, Net Income, Assets, Liabilities, Equity) and computes Gross & Net margins and Debt-to-Equity ratios. | **35** |
| **`translation`** | **الترجمة القانونية المعتمدة** | Bidirectional certified legal & corporate translation (EN ↔ AR) preserving exact clause numbering, tables, and monetary figures. | **20** |
| **`anomaly_audit`** | **تدقيق الاحتيال والتناقضات** | Forensic check for arithmetic mismatches, ZATCA VAT 15% calculation errors, inverted date chronologies, and contractual clause contradictions. | **25** |

#### Cryptographic Webhook Security (HMAC-SHA256)
All asynchronous webhooks dispatched by the Redis worker include cryptographic signatures to ensure zero-trust pipeline authenticity:
```http
POST https://api.mycorp.com/docuchat-webhook
Content-Type: application/json
X-DocuChat-Timestamp: 1730000000
X-DocuChat-Signature: sha256=a1b2c3d4e5f6...
```
Consumers can verify authenticity using `hmac.new(secret, timestamp + "." + body, sha256).hexdigest()`.


