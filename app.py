"""
Truth Layer — Automated PDF Fact-Checking Agent
=================================================
Upload a PDF (pitch deck, blog post, marketing one-pager, etc.), and this app:
  1. EXTRACTS specific checkable claims (stats, dates, financial/technical figures)
  2. VERIFIES each claim against live web data using Claude + the web search tool
  3. REPORTS each claim as Verified / Inaccurate / False, with the correct fact and sources

Run locally:  streamlit run app.py
Deploy:       see README.md
"""

import io
import json
import os
import re
import time
from datetime import datetime

import pandas as pd
import pdfplumber
import streamlit as st
from anthropic import Anthropic, APIStatusError

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
APP_TITLE = "🔍 Truth Layer — Automated PDF Fact-Checker"
DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_PDF_CHARS = 30000           # cap how much PDF text we send to the model
DEFAULT_MAX_CLAIMS = 12
VERDICT_STYLE = {
    "Verified":   {"emoji": "✅", "color": "#16a34a"},
    "Inaccurate": {"emoji": "⚠️", "color": "#d97706"},
    "False":      {"emoji": "❌", "color": "#dc2626"},
}

st.set_page_config(page_title="Truth Layer Fact-Checker", page_icon="🔍", layout="wide")

# --------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------

def get_api_key() -> str:
    """Resolve the Anthropic API key from secrets, env var, or sidebar input."""
    key = ""
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        pass
    if not key:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
    return key


def extract_pdf_text(file_bytes: bytes) -> str:
    """Pull plain text out of an uploaded PDF using pdfplumber."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(f"--- Page {i + 1} ---\n{page_text.strip()}")
    return "\n\n".join(text_parts)


def _extract_json_block(raw_text: str):
    """Pull the last ```json ... ``` fenced block (or last {...} object) out of a model response."""
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw_text, re.DOTALL)
    candidate = fenced[-1] if fenced else None
    if not candidate:
        braces = re.findall(r"(\{.*\}|\[.*\])", raw_text, re.DOTALL)
        candidate = braces[-1] if braces else None
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # last resort: try to repair trailing commas
        cleaned = re.sub(r",\s*([\]}])", r"\1", candidate)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


def extract_claims(client: Anthropic, model: str, document_text: str, max_claims: int):
    """Step 1: Ask Claude to pull out specific, checkable factual claims from the document."""
    system_prompt = (
        "You are a meticulous fact-extraction engine. You read marketing/business documents "
        "and pull out ONLY specific, independently verifiable factual claims: statistics, "
        "percentages, dates, financial figures, market sizes, technical specs, counts, rankings, "
        "or named comparisons (e.g. 'fastest-growing', 'market leader'). "
        "Ignore vague marketing fluff, opinions, and claims with no concrete checkable number/date/fact. "
        f"Return AT MOST {max_claims} of the most significant claims. "
        "Respond with ONLY a JSON array, nothing else, no preamble, no markdown fences. "
        "Each item must have exactly these keys: "
        '"claim" (the exact claim as a short standalone sentence), '
        '"original_context" (the verbatim sentence/snippet from the document it came from), '
        '"category" (one of: statistic, date, financial, technical, ranking_or_comparison).'
    )
    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Document text:\n\n{document_text}"}],
    )
    raw = "".join(b.text for b in response.content if b.type == "text")
    claims = _extract_json_block(raw)
    if claims is None:
        try:
            claims = json.loads(raw)
        except json.JSONDecodeError:
            claims = []
    return claims if isinstance(claims, list) else []


def verify_claim(client: Anthropic, model: str, claim: dict):
    """Step 2: Use Claude + the live web_search tool to verify a single claim."""
    system_prompt = (
        "You are a rigorous fact-checker. You will be given one specific claim extracted from a "
        "document. Use web search to find current, authoritative, real-world information relevant "
        "to this exact claim, then classify it:\n"
        "- 'Verified': the claim matches current, credible data.\n"
        "- 'Inaccurate': there IS real data on this topic, but the document's number/date/fact is "
        "wrong or outdated compared to what you found.\n"
        "- 'False': you can find no credible evidence supporting the claim, or it appears fabricated "
        "or contradicted outright.\n\n"
        "After researching, respond with ONLY a single fenced ```json block as the LAST thing in your "
        "reply, with exactly these keys:\n"
        '{"verdict": "Verified"|"Inaccurate"|"False", '
        '"correct_fact": "<the accurate figure/date/fact you found, or null if Verified>", '
        '"explanation": "<1-2 sentence reasoning>", '
        '"sources": ["<url1>", "<url2>"]}'
    )
    user_msg = (
        f"Claim to verify: {claim.get('claim')}\n"
        f"Original context from document: {claim.get('original_context', '')}\n"
        f"Category: {claim.get('category', 'unknown')}"
    )
    response = client.messages.create(
        model=model,
        max_tokens=1500,
        system=system_prompt,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}],
        messages=[{"role": "user", "content": user_msg}],
    )

    raw_text_parts = []
    cited_sources = []
    for block in response.content:
        if block.type == "text":
            raw_text_parts.append(block.text)
            citations = getattr(block, "citations", None) or []
            for c in citations:
                url = getattr(c, "url", None)
                title = getattr(c, "title", None)
                if url:
                    cited_sources.append({"url": url, "title": title or url})

    raw = "".join(raw_text_parts)
    result = _extract_json_block(raw) or {}

    verdict = result.get("verdict", "False")
    if verdict not in VERDICT_STYLE:
        verdict = "False"

    sources = result.get("sources") or []
    if not sources and cited_sources:
        sources = [s["url"] for s in cited_sources]
    # de-dupe, cap at 3
    seen = set()
    clean_sources = []
    for s in sources:
        if s and s not in seen:
            seen.add(s)
            clean_sources.append(s)
        if len(clean_sources) >= 3:
            break

    return {
        "claim": claim.get("claim"),
        "original_context": claim.get("original_context", ""),
        "category": claim.get("category", "unknown"),
        "verdict": verdict,
        "correct_fact": result.get("correct_fact"),
        "explanation": result.get("explanation", "No explanation returned."),
        "sources": clean_sources,
    }


def build_markdown_report(filename: str, results: list) -> str:
    counts = {"Verified": 0, "Inaccurate": 0, "False": 0}
    for r in results:
        counts[r["verdict"]] += 1
    lines = [
        f"# Fact-Check Report: {filename}",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        f"**Summary:** {counts['Verified']} Verified · {counts['Inaccurate']} Inaccurate · {counts['False']} False",
        "",
        "---",
        "",
    ]
    for r in results:
        emoji = VERDICT_STYLE[r["verdict"]]["emoji"]
        lines.append(f"## {emoji} {r['verdict']} — {r['claim']}")
        lines.append(f"- **Original text in document:** \"{r['original_context']}\"")
        lines.append(f"- **Category:** {r['category']}")
        if r["correct_fact"]:
            lines.append(f"- **Correct fact:** {r['correct_fact']}")
        lines.append(f"- **Explanation:** {r['explanation']}")
        if r["sources"]:
            lines.append("- **Sources:**")
            for s in r["sources"]:
                lines.append(f"  - {s}")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

st.title(APP_TITLE)
st.caption(
    "Upload a PDF — pitch deck, blog post, press release — and this tool extracts every "
    "checkable claim, verifies it against live web data, and flags what's wrong."
)

with st.sidebar:
    st.header("⚙️ Settings")
    api_key_input = get_api_key()
    if not api_key_input:
        api_key_input = st.text_input(
            "Anthropic API Key", type="password",
            help="Get one at https://console.anthropic.com/settings/keys. "
                 "On Streamlit Cloud, set this as a secret instead (see README)."
        )
    else:
        st.success("API key loaded from secrets/environment ✓")

    model_choice = st.selectbox(
        "Model",
        options=["claude-sonnet-4-6", "claude-opus-4-7"],
        index=0,
        help="Sonnet is fast and cheap. Opus is slower but more thorough — use it on tricky documents.",
    )
    max_claims = st.slider("Max claims to check", min_value=3, max_value=25, value=DEFAULT_MAX_CLAIMS)

    st.divider()
    st.markdown(
        "**How it works**\n"
        "1. Extract text from your PDF\n"
        "2. Claude identifies checkable claims\n"
        "3. Claude + live web search verifies each one\n"
        "4. You get a Verified / Inaccurate / False report\n"
    )
    st.divider()
    use_sample = st.button("📄 Try it on a sample 'trap document'")

uploaded_file = st.file_uploader("Upload a PDF", type=["pdf"])

# Allow loading the bundled sample trap document for a quick test
sample_path = os.path.join(os.path.dirname(__file__), "sample_data", "trap_document.pdf")
if use_sample and os.path.exists(sample_path):
    with open(sample_path, "rb") as f:
        uploaded_file = io.BytesIO(f.read())
        uploaded_file.name = "trap_document.pdf"

run = st.button("🚀 Run Fact-Check", type="primary", disabled=uploaded_file is None)

if run:
    if not api_key_input:
        st.error("Please provide an Anthropic API key in the sidebar first.")
        st.stop()

    client = Anthropic(api_key=api_key_input)
    file_bytes = uploaded_file.read() if hasattr(uploaded_file, "read") else uploaded_file.getvalue()

    with st.status("Reading PDF…", expanded=True) as status:
        document_text = extract_pdf_text(file_bytes)
        if not document_text.strip():
            status.update(label="No extractable text found.", state="error")
            st.error(
                "Couldn't find any text in this PDF. If it's a scanned/image-based PDF, OCR isn't "
                "supported in this version — try a text-based PDF."
            )
            st.stop()
        document_text = document_text[:MAX_PDF_CHARS]
        status.update(label=f"Extracted {len(document_text):,} characters of text ✓")

        status.write("🔎 Identifying checkable claims…")
        try:
            claims = extract_claims(client, model_choice, document_text, max_claims)
        except APIStatusError as e:
            status.update(label="Claude API error during claim extraction.", state="error")
            st.error(f"API error: {e}")
            st.stop()

        if not claims:
            status.update(label="No checkable claims found.", state="error")
            st.warning(
                "No specific stats/dates/figures were found to fact-check. "
                "This document may be too vague, or text extraction may have failed."
            )
            st.stop()

        status.update(label=f"Found {len(claims)} claims. Verifying against live web data…")

        results = []
        progress = st.progress(0.0)
        for i, claim in enumerate(claims):
            status.write(f"  Checking claim {i + 1}/{len(claims)}: _{claim.get('claim', '')[:90]}_")
            try:
                result = verify_claim(client, model_choice, claim)
            except APIStatusError as e:
                result = {
                    "claim": claim.get("claim"),
                    "original_context": claim.get("original_context", ""),
                    "category": claim.get("category", "unknown"),
                    "verdict": "False",
                    "correct_fact": None,
                    "explanation": f"Verification failed due to an API error: {e}",
                    "sources": [],
                }
            results.append(result)
            progress.progress((i + 1) / len(claims))
            time.sleep(0.1)

        status.update(label="✅ Fact-check complete!", state="complete")

    st.session_state["results"] = results
    st.session_state["filename"] = getattr(uploaded_file, "name", "document.pdf")

# --------------------------------------------------------------------------
# RESULTS DISPLAY
# --------------------------------------------------------------------------
if "results" in st.session_state:
    results = st.session_state["results"]
    filename = st.session_state["filename"]

    counts = {"Verified": 0, "Inaccurate": 0, "False": 0}
    for r in results:
        counts[r["verdict"]] += 1

    st.subheader(f"Results for `{filename}`")
    c1, c2, c3 = st.columns(3)
    c1.metric("✅ Verified", counts["Verified"])
    c2.metric("⚠️ Inaccurate", counts["Inaccurate"])
    c3.metric("❌ False", counts["False"])

    st.divider()

    for r in results:
        style = VERDICT_STYLE[r["verdict"]]
        with st.container(border=True):
            st.markdown(
                f"<span style='color:{style['color']}; font-weight:700; font-size:1.05em;'>"
                f"{style['emoji']} {r['verdict']}</span> — {r['claim']}",
                unsafe_allow_html=True,
            )
            st.caption(f"📄 As written in the document: \"{r['original_context']}\"")
            if r["correct_fact"]:
                st.markdown(f"**Correct fact:** {r['correct_fact']}")
            st.write(r["explanation"])
            if r["sources"]:
                st.markdown("**Sources:** " + " · ".join(f"[{i+1}]({s})" for i, s in enumerate(r["sources"])))

    st.divider()
    report_md = build_markdown_report(filename, results)
    df = pd.DataFrame(results)

    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "⬇️ Download Markdown report", report_md,
            file_name=f"factcheck_{filename.rsplit('.', 1)[0]}.md", mime="text/markdown",
        )
    with dl2:
        st.download_button(
            "⬇️ Download CSV", df.to_csv(index=False),
            file_name=f"factcheck_{filename.rsplit('.', 1)[0]}.csv", mime="text/csv",
        )
