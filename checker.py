# checker.py
import os
import json
import re
import google.generativeai as genai
from typing import List
from rag_loader import load_vectorstore

# configure Gemini (for LLM)
GEN_KEY = os.getenv("GEMINI_API_KEY")
if GEN_KEY:
    genai.configure(api_key=GEN_KEY)
else:
    # keep quiet; will raise later if we attempt to call Gemini without key
    pass

# Helper: simple text snippet cleaning
def _clean_snippet(s: str, length=1000):
    s = s.strip()
    if len(s) > length:
        return s[:length] + "..."
    return s

def retrieve_context(vectorstore, query, k=4, category_filter=None):
    """
    Fetch top-k relevant chunks from vectorstore.
    If category_filter provided, attempt to filter by metadata category.
    Returns concatenated context string.
    """
    # If vectorstore supports metadata filters, implement them; otherwise do plain similarity.
    try:
        if category_filter and hasattr(vectorstore, "similarity_search_with_relevance_scores"):
            docs = vectorstore.similarity_search(query, k=k)
        else:
            docs = vectorstore.similarity_search(query, k=k)
    except Exception:
        docs = []

    if not docs:
        return ""
    pieces = []
    for d in docs:
        meta = getattr(d, 'metadata', {}) or {}
        src = meta.get('source', meta.get('url', 'unknown'))
        snippet = _clean_snippet(getattr(d, 'page_content', ''))
        pieces.append(f"Source: {src}\n{snippet}")
    return "\n\n".join(pieces)

def _simple_heuristic_checks(clause_text, paragraph_index):
    """
    Heuristic (non-LLM) checks that produce issue dicts.
    """
    issues = []
    lt = clause_text.lower()

    # Incorrect jurisdiction examples
    if re.search(r'\b(uae federal courts|federal courts of the uae|uae courts)\b', lt):
        issues.append({
            "paragraph_index": paragraph_index,
            "issue": "Incorrect jurisdiction referenced (mentions UAE federal courts).",
            "severity": "High",
            "suggestion": "Replace with explicit ADGM jurisdiction clause, e.g. 'This agreement is governed by the laws of the Abu Dhabi Global Market (ADGM).'",
            "citation": "ADGM Companies Regulations 2020, Art. 6 (example)"
        })

    # Governing law clause present but doesn't mention ADGM
    if "governed by" in lt and "adgm" not in lt:
        issues.append({
            "paragraph_index": paragraph_index,
            "issue": "Governing law clause present but does not specify ADGM.",
            "severity": "High",
            "suggestion": "Modify governing law clause to explicitly reference ADGM jurisdiction.",
            "citation": "ADGM Companies Regulations 2020, Art. 6 (example)"
        })

    # Missing signature lines heuristic
    if not re.search(r'signature|signed by|signature:\s|for and on behalf of', lt):
        # only warn for clauses that look like closing/execution blocks or full agreements
        if len(lt) > 200 and any(k in lt for k in ["agreement", "this agreement", "in witness"]):
            issues.append({
                "paragraph_index": paragraph_index,
                "issue": "Possible missing signature / execution block.",
                "severity": "Medium",
                "suggestion": "Ensure there is a signature block with printed name, title and date.",
                "citation": "ADGM execution signature guidance (template)"
            })

    # Ambiguous language detection
    ambiguous_phrases = [
        "best efforts", "reasonable endeavours", "endeavour", "as soon as reasonably practicable",
        "subject to availability", "to the extent possible", "where possible"
    ]
    for p in ambiguous_phrases:
        if p in lt:
            issues.append({
                "paragraph_index": paragraph_index,
                "issue": f"Ambiguous/non-binding phrase detected: '{p}'.",
                "severity": "Low",
                "suggestion": f"Consider replacing '{p}' with a precise obligation or timescale.",
                "citation": ""
            })
            break

    # UBO mention check (if clause relates to ownership but no UBO mention)
    if any(k in lt for k in ["shareholder", "shares", "beneficial owner"]) and "ubo" not in lt and "ultimate beneficial owner" not in lt:
        issues.append({
            "paragraph_index": paragraph_index,
            "issue": "Clause concerns ownership/shareholders but UBO disclosures are not referenced.",
            "severity": "Medium",
            "suggestion": "Ensure the document includes/links to an UBO declaration form where relevant.",
            "citation": "ADGM registry/UBO guidance (check ADGM docs)"
        })

    return issues

def _safe_parse_json(text):
    """
    Safely parse JSON from a model response that may contain extra text.
    Attempts to find the first JSON array or object in the text and parse it.
    """
    text = text.strip()
    if not text:
        return None
    # try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # find first '[' ... ']' or '{' ... '}'
    first_array = re.search(r'(\[.*\])', text, flags=re.DOTALL)
    first_obj = re.search(r'(\{.*\})', text, flags=re.DOTALL)
    candidate = None
    if first_array:
        candidate = first_array.group(1)
    elif first_obj:
        candidate = first_obj.group(1)

    if candidate:
        try:
            return json.loads(candidate)
        except Exception:
            # try to fix common issues (trailing commas)
            candidate_fixed = re.sub(r',\s*([\]}])', r'\1', candidate)
            try:
                return json.loads(candidate_fixed)
            except Exception:
                return None
    return None

def check_clause(clause_text: str, paragraph_index: int, vectorstore, model="gemini-pro"):
    """
    Return a list of issue dicts for a clause. Uses RAG + Gemini with a JSON-only response.
    Each issue dict will contain: paragraph_index, issue, severity (Low/Medium/High), suggestion, citation, alt_clause (optional).
    """

    # Heuristic checks first (fast)
    issues = _simple_heuristic_checks(clause_text, paragraph_index)

    # Retrieve RAG context
    context = retrieve_context(vectorstore, clause_text, k=4)

    # Build a rich system/user prompt instructing the LLM to output JSON
    system = (
        "You are an ADGM legal compliance assistant. You will analyze a single clause and return ONLY valid JSON.\n"
        "The JSON must be an array of objects. Each object MUST have the keys:\n"
        "paragraph_index, issue, severity (Low/Medium/High), suggestion, citation.\n"
        "OPTIONAL keys: alt_clause (a recommended alternative clause wording), clause_type (e.g., Governing Law, Execution, UBO, Signature), confidence (0-1 float).\n"
        "Do NOT include any extra commentary outside the JSON array."
    )

    prompt = (
        f"Context (ADGM reference materials):\n{context}\n\n"
        f"Clause (to analyze):\n{clause_text}\n\n"
        "Tasks:\n"
        "1. Detect red flags: incorrect jurisdiction, missing or invalid clauses, ambiguous wording, missing signatory, formatting issues, non-compliance with ADGM templates.\n"
        "2. For each issue provide a suggestion and, where possible, an alternative clause wording (alt_clause) that would be compliant.\n"
        "3. Provide a citation pointing to the ADGM law, regulation or template if possible (give section/article if available).\n"
        "4. Output ONLY valid JSON as described. If there are no issues, output an empty array: []\n"
    )

    # If model key not configured, skip LLM and return heuristics only
    if not GEN_KEY:
        return issues

    try:
        model_obj = genai.GenerativeModel(model)
        resp = model_obj.generate_content(
            [{"role": "system", "parts": [system]}, {"role": "user", "parts": [prompt]}],
            temperature=0.0,
            max_output_tokens=800
        )
        text = resp.text.strip()
        parsed = _safe_parse_json(text)
        if parsed is None:
            # fallback: attempt to extract heuristics only
            return issues
        # Ensure paragraph_index present
        out = []
        for it in parsed:
            if isinstance(it, dict):
                it.setdefault("paragraph_index", paragraph_index)
                # ensure required keys exist minimally
                if "issue" in it and "severity" in it and "suggestion" in it:
                    out.append(it)
        # combine model-found issues with heuristics deduped by 'issue' text
        existing_issues_texts = {i['issue'] for i in issues}
        for o in out:
            if o.get('issue') not in existing_issues_texts:
                issues.append(o)
        return issues

    except Exception as e:
        # On any exception, return heuristics only
        heur = issues
        return heur
