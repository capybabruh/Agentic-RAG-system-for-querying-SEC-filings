# Data

Local data artifacts for development live here.

- `downloads/` holds raw source files fetched from SEC EDGAR, grouped by year.
- `markdown/` holds Docling-converted Markdown files with the same year-folder layout.
- Downloaded payloads are gitignored because the corpus can get large.
- Fetch a sample corpus with `uv run data/download.py` 

## Convert HTML filings to Markdown

Docling is installed in the backend development environment. From `backend/`, run:

```powershell
uv run python ../data/convert_to_markdown.py
```

The converter reads `.htm` and `.html` files from `downloads/` recursively and writes matching `.md` files under `markdown/`. Existing Markdown files newer than their source HTML are skipped.

To reconvert every filing:

```powershell
uv run python ../data/convert_to_markdown.py --force
```

You can use different directories when needed:

```powershell
uv run python ../data/convert_to_markdown.py --input-dir ../data/downloads --output-dir ../data/markdown
```

## Import Markdown into Supabase

From `backend/`, after applying the Alembic migration, run:

```powershell
uv run python ../data/ingest_documents.py
```

The script imports the converted filings into the `source_documents` table. It uses the SEC `source_url` as the stable identity, so rerunning it skips existing documents. Use `--update` to refresh existing rows from their Markdown files:

```powershell
uv run python ../data/ingest_documents.py --update
```

## Create chunks and Mistral embeddings

The chunk pipeline uses Docling's `HybridChunker` and Mistral's `mistral-embed` model. Mistral embeddings are 1024-dimensional, matching the current `document_chunks.embedding` column.

Configure `MISTRAL_API_KEY` in `backend/.env`, apply the embedding-dimension migration, and run the one-chunk smoke test first:

```powershell
cd backend
uv run alembic upgrade head
uv run python ../data/ingest_chunks.py --smoke-test
```

After the smoke test verifies the vector and generated full-text search column, run the full corpus:

```powershell
uv run python ../data/ingest_chunks.py
```
