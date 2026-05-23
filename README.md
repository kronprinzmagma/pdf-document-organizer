# dok-namer

Automatically rename scanned documents using AI — with a privacy-first pipeline that never sends your personal data to the cloud.

---

## The Problem

Scanned documents pile up with names like `scan0042.pdf`, `document_final_v3.pdf`, or whatever your scanner defaults to. Finding a letter from three years ago means opening every file one by one.

The obvious fix — send the document to an AI and ask it to extract the sender, date, and topic — has a real problem: personal documents contain names, IBANs, AHV numbers, addresses, account numbers, and medical information. Sending that to a cloud API is a privacy risk that stops most people from automating this.

dok-namer solves that. It analyses your PDFs, suggests structured filenames, and organises them into topic folders — without ever sending your raw personal data to the cloud.

---

## The Solution

dok-namer reads each PDF, strips all personally identifiable information before any cloud call, then uses an AI to extract the document's sender, content type, and date. The result is a clean, searchable filename like:

```
Swisscom-Rechnung-20250301.pdf
```

Documents are then automatically sorted into topic folders under `done/`.

Three engines are available depending on your privacy and performance requirements:

| Engine | How it works | Best for |
|--------|-------------|----------|
| `claude` | Regex redaction in memory, then Claude Haiku | Fastest; reliable for structured PII |
| `ollama` | Fully local via llava/llama3.2 — no cloud calls | Maximum privacy; slower |
| `hybrid` | Local LLM anonymises first, regex verifies, then Claude | Highest confidence for mixed documents |

### Interactive workflow

In the default interactive mode, you confirm each rename before it happens:

```
File: scan0042.pdf
  Analysing... (Engine: claude)
  Redactions: 2x [NAME], 1x [IBAN]
  Tokens: 312 in / 48 out  |  Cost: CHF 0.0002
  Confidence: high
  Suggested filename: Swisscom-Rechnung-20250301.pdf
  Accept? [y/n]: y
  → Moved to: done/05_Housing-Utilities/Swisscom-Rechnung-20250301.pdf
```

You can accept the suggestion, type a custom filename stem, or skip the file.

---

## Privacy Architecture

### The trust problem

Cloud APIs are powerful, but personal documents contain names, IBANs, social security numbers, addresses, and medical details. Even if an API provider promises not to store data, the safest approach is to ensure that sensitive data never leaves your machine in the first place.

### How the redaction pipeline works

Before any text reaches a cloud API, dok-namer applies a multi-layer redaction pipeline entirely in memory:

**Step 1 — Text extraction**
pypdf extracts text from the PDF locally. The original file is never modified.

**Step 2 — Regex redaction (always applied)**
A set of compiled regex patterns strips structured PII from the extracted text, replacing each match with a labelled placeholder:

| Pattern | Replaced with |
|---------|--------------|
| IBAN (Swiss and international) | `[IBAN]` |
| Swiss AHV social security number | `[AHV]` |
| Email addresses | `[EMAIL]` |
| Swiss and international phone numbers | `[TELEFON]` |
| Amounts with currency symbols (CHF, EUR, USD) | `[BETRAG]` |
| Swiss postal addresses | `[ADRESSE]` |
| Academic and medical titles + names (Dr., Prof., etc.) | `[BEHANDLER]` |

An optional personal blocklist (`redact-names.txt`) handles names that regex cannot catch — one name per line, applied case-insensitively after the regex pass.

**Step 3 — Cloud call (with redacted text only)**
Only the redacted text — containing none of the original PII — is sent to Claude Haiku. The API extracts sender, content type, date, and confidence level as structured output.

### Hybrid mode: defence in depth

The `hybrid` engine adds a local LLM pass before the regex verification:

1. llama3.2 reads the raw text and replaces names and identifiers with placeholders
2. Regex verification checks whether any AHV numbers or Swiss mobile numbers survived the LLM pass
3. Only if the text is clean does it proceed to Claude Haiku

This two-pass approach catches PII that neither regex alone nor an LLM alone would reliably handle.

### Scan PDFs are blocked entirely

If a PDF contains no extractable text (a scanned image with no OCR layer), dok-namer cannot apply the redaction pipeline. Rather than risk sending an unredacted image to the cloud, it routes the file to `review/` for manual handling. No cloud call is made.

### The original file is never modified

Redaction happens in memory, on the extracted text only. The source PDF is read once, then either moved to its destination folder or left in place. Its contents are never altered.

---

## Output Structure

After processing a folder, files are organised as follows:

```
your-documents/
├── done/
│   ├── 01_Taxes-Government/
│   ├── 02_Banking-Pension/
│   ├── 03_Health-Insurance/
│   ├── 04_Insurance/
│   ├── 05_Housing-Utilities/
│   ├── 06_Work-Income/
│   ├── 07_Children-Education/
│   ├── 08_Mobility/
│   ├── 09_Shopping-Memberships/
│   ├── 10_Personal-Legal/
│   └── 99_Other/
├── unrecognized/    # low-confidence extractions — review manually
├── review/          # needs manual check (scan PDFs, uncertain PII)
└── error/           # technical failures — see dok-namer-log.jsonl
```

Categories are assigned automatically by matching the suggested filename against keyword rules — no additional API call is required for categorisation.

The category system is customisable via a `categories.yaml` file (see [Usage](#usage)).

---

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# For hybrid or ollama engines:
ollama pull llama3.2
ollama pull llava
```

---

## Usage

```bash
# Single file — interactive
python dok_namer.py path/to/file.pdf

# Folder — interactive (confirms each rename)
python dok_namer.py /path/to/pdfs

# Folder — unattended batch, 4 parallel workers (fastest)
python dok_namer.py /path/to/pdfs --engine claude --auto --workers 4

# Fully local — no cloud calls at all
python dok_namer.py /path/to/pdfs --engine ollama --auto

# Hybrid — local LLM anonymisation + cloud extraction
python dok_namer.py /path/to/pdfs --engine hybrid --auto

# Custom categories
cp categories.yaml.example categories.yaml
# edit categories.yaml to match your document types, then:
python dok_namer.py /path/to/pdfs --config categories.yaml
```

### Resumability

Every processed file is logged to `dok-namer-log.jsonl` in the source folder. If a run is interrupted, re-running the same command picks up where it left off — already-processed files that have been moved are skipped automatically.

### Rate limits and retries

Temporary Claude API errors (rate limits, timeouts, overload) are retried automatically with exponential backoff before a file is routed to `error/`.

---

## Tech Stack

- **Python 3** — single-file script, no package structure required
- **Claude Haiku** (`claude-haiku-4-5-20251001`) via Anthropic API — structured output extracted using Pydantic models via `client.messages.parse()`
- **llama3.2 + llava** via Ollama — optional, for hybrid and fully local engines
- **pypdf** — PDF text extraction
- **pyyaml** — configurable category system
- **pytest** — test suite

---

## Performance

Benchmark on Apple Silicon with 20 test PDFs:

| Configuration | Total | Per file | Notes |
|---------------|-------|----------|-------|
| `--engine hybrid --workers 1` | 190 s | 9.5 s | Baseline |
| `--engine hybrid --workers 4` | 640 s | 32 s | Ollama serialises internally — parallel calls queue up |
| `--engine claude --workers 4` | **33 s** | **1.7 s** | Best throughput |

Key insight: Ollama serialises all requests per model. Multiple parallel llama3.2 calls queue internally and are slower than sequential. Parallel Claude calls scale well because the API handles concurrency server-side.

Projected throughput: 400 PDFs at 1.7 s/file across 4 workers ≈ **~170 seconds (~3 minutes)**.

---

## License

MIT License. See [LICENSE](LICENSE).

Contributions welcome — open an issue or pull request.
