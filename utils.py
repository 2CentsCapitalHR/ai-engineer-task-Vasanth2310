# utils.py

CHECKLIST = {
    "Company Incorporation": [
        "Articles of Association",
        "Memorandum of Association",
        "Board Resolution",
        "Shareholder Resolution",
        "Incorporation Application Form",
        "UBO Declaration Form",
        "Register of Members and Directors",
        "Change of Registered Address Notice"
    ],
    "Employment & HR": [
        "Standard Employment Contract",
        "Employee Handbook",
        "Offer Letter"
    ],
    "Licensing": [
        "Licensing Application Form",
        "Supporting Documents for License"
    ],
    "Compliance & Risk": [
        "Data Protection Policy",
        "Compliance Policy",
        "Risk Assessment"
    ],
    "Commercial Agreements": [
        "NDA",
        "Consultancy Agreement",
        "Service Agreement",
        "Sale/Purchase Agreement"
    ]
}

# keyword mapping for detecting document types
DOC_TYPE_KEYWORDS = {
    "Articles of Association": ["articles of association", "aoa", "article of association"],
    "Memorandum of Association": ["memorandum of association", "moa", "memorandum"],
    "Board Resolution": ["board resolution", "resolution of the board"],
    "Shareholder Resolution": ["shareholder resolution", "resolution of the shareholders", "shareholders' resolution"],
    "Incorporation Application Form": ["incorporation application", "application for incorporation", "form ra"],
    "UBO Declaration Form": ["ubo declaration", "ultimate beneficial owner", "ubo form"],
    "Register of Members and Directors": ["register of members", "register of directors", "register of members and directors"],
    "Change of Registered Address Notice": ["change of registered address", "registered address notice"],
    "Standard Employment Contract": ["employment contract", "standard employment contract", "employee contract"],
    "Offer Letter": ["offer letter", "employment offer"],
    "NDA": ["non-disclosure agreement", "nda", "confidentiality agreement"],
    "Consultancy Agreement": ["consultancy agreement", "consultant agreement"],
    "Service Agreement": ["service agreement", "services agreement"],
    "Data Protection Policy": ["data protection policy", "dpr", "data protection"],
    "Compliance Policy": ["compliance policy", "compliance manual"],
    "Licensing Application Form": ["licensing application", "license application", "application for license"]
}

# phrases that commonly indicate ambiguous or non-binding language
AMBIGUOUS_PHRASES = [
    "best efforts", "reasonable efforts", "reasonable endeavours", "endeavour to", "to the extent possible",
    "as soon as reasonably practicable", "where possible", "subject to availability", "may be required"
]

def detect_doc_type_from_text(text):
    """
    Return list of matched document types based on keyword matching.
    Input: text (str)
    Output: list of doc type names
    """
    t = text.lower()
    matches = set()
    for doc_name, kws in DOC_TYPE_KEYWORDS.items():
        for kw in kws:
            if kw in t:
                matches.add(doc_name)
                break
    return list(matches)

def detect_process_from_uploaded_types(uploaded_types):
    """
    Heuristic to determine the legal process based on uploaded document types.
    uploaded_types: iterable of doc type strings (e.g., "Articles of Association")
    Returns process name string or None.
    """
    uploaded_set = set(uploaded_types)
    # Incorporation if we have AoA or MoA or Incorporation Application
    incorporation_indicators = {"Articles of Association", "Memorandum of Association", "Incorporation Application Form", "Register of Members and Directors"}
    if uploaded_set & incorporation_indicators:
        return "Company Incorporation"

    # Employment if any employment docs present
    if uploaded_set & set(CHECKLIST.get("Employment & HR", [])):
        return "Employment & HR"

    # Licensing
    if uploaded_set & set(CHECKLIST.get("Licensing", [])):
        return "Licensing"

    # Compliance & Risk
    if uploaded_set & set(CHECKLIST.get("Compliance & Risk", [])):
        return "Compliance & Risk"

    # Commercial Agreements
    if uploaded_set & set(CHECKLIST.get("Commercial Agreements", [])):
        return "Commercial Agreements"

    # default fallback
    return None

def checklist_comparison_for_process(process, uploaded_types):
    """
    Returns (required_list, missing_list, uploaded_count, required_count)
    """
    required = CHECKLIST.get(process, [])
    missing = list(set(required) - set(uploaded_types))
    return required, missing, len(uploaded_types), len(required)

def build_user_checklist_message(process, uploaded_types):
    """
    Build a friendly message similar to the example you provided.
    """
    required, missing, uploaded_count, required_count = checklist_comparison_for_process(process, uploaded_types)
    if missing:
        missing_names = "', '".join(missing)
        msg = (
            f"It appears that you’re trying to {('incorporate a company in ADGM' if process=='Company Incorporation' else 'perform the process: ' + process)}. "
            f"Based on our reference list, you have uploaded {uploaded_count} out of {required_count} required documents. "
            f"The missing document(s) appears to be: '{missing_names}'."
        )
    else:
        msg = (
            f"It appears that you’re trying to {('incorporate a company in ADGM' if process=='Company Incorporation' else 'perform the process: ' + process)}. "
            f"All required documents ({required_count}) appear to be uploaded."
        )
    return msg
