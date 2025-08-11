# app.py
import os
import io
import json
import tempfile
import streamlit as st
from rag_loader import load_vectorstore
from doc_parser import parse_docx, annotate_docx
from checker import check_clause
from utils import detect_doc_type_from_text, detect_process_from_uploaded_types, CHECKLIST, build_user_checklist_message

st.set_page_config(page_title='ADGM Corporate Agent — Demo', layout='wide')
st.title('ADGM Corporate Agent — Demo')

st.markdown('Upload `.docx` files (company formation docs and others). The demo will check key clauses using RAG and an LLM, and verify document checklists.')

uploaded_files = st.file_uploader('Upload .docx files', accept_multiple_files=True, type=['docx'])

# Load vectorstore (expect it has been built using rag_loader.py)
VSTORE_PATH = 'chroma_db'
try:
    vectordb = load_vectorstore(VSTORE_PATH)
    st.success('Loaded ADGM reference vectorstore.')
except Exception as e:
    st.warning('Could not load vectorstore. Please run `python rag_loader.py --build` after placing ADGM PDF/TXT/DOCX files into adgm_docs/.')
    vectordb = None

if st.button('Analyze'):
    if not uploaded_files:
        st.error('Please upload at least one .docx file to analyze.')
    elif not vectordb:
        st.error('Vectorstore not available. Build the vectorstore first (see README).')
    else:
        tmpdir = tempfile.mkdtemp()
        reports = []
        uploaded_types = set()
        annotated_outputs = []

        for u in uploaded_files:
            # save uploaded file to temp
            raw_bytes = u.read()
            in_path = os.path.join(tmpdir, u.name)
            with open(in_path, 'wb') as f:
                f.write(raw_bytes)

            paragraphs = parse_docx(in_path)
            # detect type by scanning first 15 paragraphs
            sample_txt = '\n'.join([p['text'] for p in paragraphs[:15]])
            detected = detect_doc_type_from_text(sample_txt)
            for d in detected:
                uploaded_types.add(d)

            file_issues = []
            # only check paragraphs that contain certain keywords to limit calls
            KEYWORDS = ['jurisdiction', 'govern', 'governing', 'court', 'signatur', 'director', 'member', 'ubo', 'share', 'agreement', 'witness', 'execution']
            for p in paragraphs:
                text = p['text']
                if any(k in text.lower() for k in KEYWORDS):
                    try:
                        issues = check_clause(text, p['index'], vectordb)
                        if issues:
                            file_issues.extend(issues)
                    except Exception as e:
                        st.write('LLM / check error for paragraph', p['index'], e)

            # annotate and save output
            out_name = u.name.replace('.docx', '') + '_reviewed.docx'
            out_path = os.path.join(tmpdir, out_name)
            annotate_docx(in_path, file_issues, out_path)
            annotated_outputs.append({'orig': u.name, 'annotated_path': out_path, 'issues': file_issues})

            reports.append({
                'document': u.name,
                'detected_types': detected,
                'issues_found': file_issues
            })

        # process detection & checklist
        process = detect_process_from_uploaded_types(uploaded_types) or 'Company Incorporation'
        required = CHECKLIST.get(process, [])
        missing = list(set(required) - set(uploaded_types))

        final_report = {
            'process': process,
            'documents_uploaded': len(uploaded_files),
            'uploaded_document_types': list(uploaded_types),
            'required_documents': len(required),
            'missing_documents': missing,
            'issues_found': reports
        }

        st.header('Summary')
        st.json(final_report)

        # Friendly checklist message
        checklist_msg = build_user_checklist_message(process, uploaded_types)
        st.info(checklist_msg)

        st.subheader('Checklist Status')
        st.write(f"Required documents for {process}: {required}")
        st.write(f"Missing documents: {missing}")
        st.write(f"Total issues found: {sum(len(r['issues_found']) for r in reports)}")

        st.success('Analysis complete.')

        st.markdown('### Download reviewed files & report')
        for ao in annotated_outputs:
            with open(ao['annotated_path'], 'rb') as f:
                data = f.read()
            st.download_button(label=f"Download {ao['orig']} (reviewed)", data=data, file_name=os.path.basename(ao['annotated_path']))

        st.download_button(label='Download JSON report', data=json.dumps(final_report, indent=2), file_name='report.json')
