# 🔍 Truth Layer — Automated PDF Fact-Checking Agent

Upload a PDF (pitch deck, marketing one-pager, blog post). The app:

1. **Extracts** specific, checkable claims — stats, dates, financial figures, technical specs — from the document.
2. **Verifies** each one against **live web data** using Claude's web search tool.
3. **Reports** each claim as **✅ Verified**, **⚠️ Inaccurate** (real data exists, but the doc is wrong/outdated), or **❌ False** (no credible evidence found), along with the correct fact and source links.

**Live app:** _add your deployed URL here after step 4 below_
**Demo video:** _add your 30-second recording link here_

---

## How it works

```
PDF upload
   │
   ▼
pdfplumber  ──►  extract raw text
   │
   ▼
Claude (no tools)  ──►  extract a structured list of checkable claims (JSON)
   │
   ▼
For each claim:
   Claude + web_search tool  ──►  search live web, compare claim to reality,
                                  classify Verified / Inaccurate / False,
                                  return correct fact + sources
   │
   ▼
Streamlit UI  ──►  color-coded report + downloadable Markdown/CSV
```

Two LLM calls per run: one to extract claims, one *per claim* to verify it live against the web (Anthropic's server-side `web_search_20250305` tool — no separate search API key needed).

---

## Run it locally

```bash
git clone <your-repo-url>
cd factcheck-app
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml and paste your real Anthropic API key

streamlit run app.py
```

Get an API key at https://console.anthropic.com/settings/keys (the account needs credits/billing enabled for API usage — separate from a claude.ai subscription).

There's also a sample "trap document" bundled for quick testing — click **"Try it on a sample trap document"** in the sidebar, or regenerate it yourself:

```bash
cd sample_data && python generate_trap_pdf.py
```

It contains a deliberate mix of true, outdated, and fabricated stats (population figures, EV delivery counts, market caps, etc.) to sanity-check the pipeline before testing with a real evaluation document.

---

## Deploy it live (mandatory step — do this!)

The easiest free option is **Streamlit Community Cloud**. Total time: ~10 minutes.

### 1. Push this code to GitHub
```bash
cd factcheck-app
git add .
git commit -m "Truth Layer fact-checking app"
gh repo create truth-layer-factchecker --public --source=. --push
# (or create a repo manually on github.com and `git remote add origin <url> && git push -u origin main`)
```

### 2. Deploy on Streamlit Community Cloud
1. Go to **https://share.streamlit.io** and sign in with GitHub.
2. Click **"New app"**.
3. Pick your repo, branch `main`, and main file path `app.py`.
4. Click **"Advanced settings"** → **Secrets** → paste:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-your-real-key"
   ```
5. Click **Deploy**. Your live URL will look like `https://your-app-name.streamlit.app`.

### 3. (Alternative) Deploy on Render
1. Push to GitHub as above.
2. On https://render.com, **New → Web Service**, connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0`
5. Add an environment variable `ANTHROPIC_API_KEY` in the Render dashboard.

### 4. Record the demo
Once live, do a 30-second screen recording (QuickTime, Loom, or OS screen recorder) showing: upload a PDF → click "Run Fact-Check" → results appear with verdicts. Upload it anywhere shareable (Loom, Google Drive, YouTube unlisted) and drop the link at the top of this README.

---

## Project structure

```
factcheck-app/
├── app.py                          # the whole app: extraction, verification, UI
├── requirements.txt
├── README.md
├── .streamlit/
│   ├── config.toml                 # theme
│   └── secrets.toml.example        # template — copy to secrets.toml locally
└── sample_data/
    ├── generate_trap_pdf.py        # builds a sample test PDF with fake/outdated stats
    └── trap_document.pdf
```

## Configuration knobs (sidebar, no code changes needed)
- **Model**: `claude-sonnet-4-6` (fast/cheap, default) or `claude-opus-4-7` (slower, more thorough — better for subtle/technical claims).
- **Max claims to check**: caps API cost/latency per run (default 12).

## Limitations / honest notes
- **Scanned/image-only PDFs** aren't OCR'd in this version — only text-based PDFs are supported. (Easy to add `pytesseract` if needed.)
- Verdicts are only as good as what's findable on the public web — claims about private/internal company data the model can't search for will usually come back **False** ("no evidence found"), which matches the assignment's own definition of False.
- Each claim costs one API call with web search enabled — large documents are capped (`MAX_PDF_CHARS`, `max_claims` in the sidebar) to control cost and runtime.
- This is a single-file app by design for evaluation clarity; for production you'd want caching, retries, and a queue for larger documents.

## License
MIT — do whatever you want with it.
