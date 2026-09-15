# Document Copilot — pipeline flowchart

This is a project-wide flowchart: how a SEC filing becomes a searchable chunk, and how an analyst's question becomes a cited answer. It complements [architecture.md](architecture.md) (system design and rationale) and [pipeline.md](pipeline.md) (line-by-line code walkthrough of a single chat turn). Start here for the shape of the whole project; go to `pipeline.md` when you need exact function names and call order.

Diagrams use Mermaid `flowchart` syntax — rectangles are processing steps, diamonds are decisions, cylinders are database storage. View in a Markdown preview that renders Mermaid.

## 1. End to end: two pipelines, one corpus

Document Copilot is really two pipelines that share one database. The **ingestion pipeline** (offline, run by a developer/operator) fills `source_documents` and `document_chunks`. The **chat pipeline** (online, triggered by an analyst) reads from those same tables to answer questions. Nothing in the chat pipeline downloads or indexes filings — if the corpus is empty, retrieval returns nothing.

```mermaid
flowchart LR
    subgraph Ingestion["Ingestion pipeline — offline, run manually"]
        direction TB
        A1[SEC EDGAR] --> A2[Download 10-Ks<br/>data/download.py]
        A2 --> A3[Convert HTML to Markdown<br/>data/convert_to_markdown.py]
        A3 --> A4[Import source documents<br/>data/ingest_documents.py]
        A4 --> A5[Chunk + embed<br/>data/ingest_chunks.py]
    end

    A5 --> DB[("Supabase Postgres<br/>source_documents<br/>document_chunks<br/>pgvector + full-text index")]

    subgraph Chat["Chat pipeline — online, per question"]
        direction TB
        B1[Analyst asks a question] --> B2[FastAPI /chat/stream]
        B2 --> B3[PydanticAI agent<br/>+ hybrid retrieval]
        B3 --> B4[Validate citations]
        B4 --> B5[Stream cited answer]
    end

    DB -.->|"searched by"| B3
    B4 -.->|"assistant message + citations"| DB
```

## 2. Ingestion pipeline in detail

Four scripts, run in order, each depending on the previous step's output. Re-running a step is safe by default (it skips what's already done) and destructive only when `--update` / `--force` is passed.

```mermaid
flowchart TD
    Start(["Operator runs data/download.py"]) --> Download["Download 10-Ks for<br/>AAPL, MSFT, NVDA, AMZN, GOOGL<br/>from SEC EDGAR"]
    Download --> RawHTML[("data/downloads/&lt;year&gt;/*.htm<br/>+ manifest.json")]

    RawHTML --> Convert["Convert HTML to Markdown<br/>data/convert_to_markdown.py<br/>via Docling"]
    Convert --> MD[("data/markdown/&lt;year&gt;/*.md")]

    MD --> ImportCheck{"source_documents<br/>row exists?"}
    ImportCheck -->|"no, or --update"| Import["Import + manifest metadata<br/>data/ingest_documents.py"]
    ImportCheck -->|"yes, skip"| Chunk
    Import --> SourceDocs[("source_documents")]
    SourceDocs --> Chunk

    RawHTML --> Chunk["Chunk + embed<br/>data/ingest_chunks.py"]
    Chunk --> ChunkCheck{"filing already<br/>has chunks?"}
    ChunkCheck -->|"yes, skip unless --update"| Done(["Corpus ready for retrieval"])
    ChunkCheck -->|"no"| Structure["Re-parse original HTML with Docling<br/>HybridChunker, ~800-token budget<br/>keeps heading context + table headers"]
    Structure --> Embed["Mistral mistral-embed<br/>batches of 64, 1024-dim vectors"]
    Embed --> Store["Insert document_chunks<br/>text + vector + token count + page/section metadata"]
    Store --> Index["Postgres generates tsvector<br/>GIN index (full-text) +<br/>HNSW index (vector)"]
    Index --> Done
```

Key coupling: chunk creation re-reads the *original HTML* (not the stored Markdown) so it can use document structure and provenance — refreshing a filing's Markdown alone does not refresh its chunks.

## 3. Chat pipeline in detail

One analyst turn, from keystroke to rendered citation chips. The agent can loop through retrieval more than once before answering — shown as the arrow back from retrieval to the agent.

```mermaid
flowchart TD
    Q["Analyst submits a question"] --> Send["Frontend POST /chat/stream<br/>Supabase bearer token"]
    Send --> AuthCheck{"Token valid +<br/>thread owned by user?"}
    AuthCheck -->|"no"| Reject["401 / 403 / 404"]
    AuthCheck -->|"yes"| SaveQ["Save question to chat_messages<br/>commit immediately"]

    SaveQ --> Agent["PydanticAI agent runs<br/>Mistral mistral-small-latest"]
    Agent -.->|"status + heartbeats"| Status["Live status line in UI"]

    Agent --> Decide{"Agent's next move?"}
    Decide -->|"search_filings /<br/>read_chunk /<br/>read_surrounding_chunks"| Retrieve["Hybrid retrieval<br/>(embed + keywords → vector search<br/>+ full-text search → RRF fusion)"]
    Retrieve -->|"passages, chunk ids recorded"| Agent

    Decide -->|"enough evidence gathered"| Answer["GroundedAnswer:<br/>text + citations + evidence flag"]
    Answer --> Validate{"Every citation was<br/>actually retrieved<br/>this turn?"}
    Validate -->|"no"| GroundErr["Reject turn<br/>SSE error — nothing saved"]
    Validate -->|"yes"| SaveA[("Save assistant message<br/>+ citations, commit")]

    SaveA --> Stream["Stream text_delta →<br/>citations → done"]
    Stream --> Render["Browser renders Markdown<br/>+ citation chips + evidence badge"]
```

### Retrieval, zoomed in

`search_filings` is the only tool that runs the full hybrid search; `read_chunk` and `read_surrounding_chunks` skip straight to loading specific rows by ID.

```mermaid
flowchart TD
    Tool["search_filings(query, ticker?, filing_type?)"] --> Prep["Prepare query"]
    Prep --> Embed["Embed query<br/>Mistral mistral-embed"]
    Prep --> Keywords["Extract 3-5 keywords<br/>Mistral chat call"]
    Embed --> Ready(("both ready"))
    Keywords --> Ready
    Ready --> Vector["Vector search<br/>pgvector cosine distance<br/>top 50 candidates"]
    Vector --> Fulltext["Full-text search<br/>Postgres ts_rank<br/>top 50 candidates"]
    Fulltext --> Fusion["Reciprocal Rank Fusion<br/>1/(60+rank), keep top 10"]
    Fusion --> Hydrate["Load chunk text +<br/>filing metadata"]
    Hydrate --> Result["Passages returned to agent<br/>chunk ids recorded for grounding"]

    DB[("Postgres<br/>document_chunks +<br/>source_documents")]
    Vector -.-> DB
    Fulltext -.-> DB
    Hydrate -.-> DB
```

## Where to look next

| Question | Go to |
| --- | --- |
| Why is the system built this way? | [architecture.md](architecture.md) |
| Exact function names and call order for one turn? | [pipeline.md](pipeline.md) |
| How to run ingestion locally? | [../data/README.md](../data/README.md) |
| What's shipped vs. planned? | [todo.md](todo.md) |
