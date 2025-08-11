# rag_loader.py
import os
import argparse
from langchain.docstore.document import Document as LangDoc
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma
from pdfminer.high_level import extract_text
from docx import Document as DocxDocument

def load_reference_texts(ref_dir):
    """
    Loads .pdf, .txt, .md, .docx files from ref_dir and returns list of dicts:
    {"source": filename, "text": text, "category": maybe None, "url": maybe None}
    Note: we do not download any external links here — files must be present in ref_dir.
    """
    texts = []
    if not os.path.exists(ref_dir):
        return texts

    for fname in os.listdir(ref_dir):
        path = os.path.join(ref_dir, fname)
        txt = ""
        if fname.lower().endswith('.pdf'):
            try:
                txt = extract_text(path)
            except Exception as e:
                print(f"Failed to extract text from {fname}: {e}")
                continue
        elif fname.lower().endswith(('.txt', '.md')):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    txt = f.read()
            except Exception as e:
                print(f"Failed to read text file {fname}: {e}")
                continue
        elif fname.lower().endswith('.docx'):
            try:
                doc = DocxDocument(path)
                txt = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
            except Exception as e:
                print(f"Failed to extract text from {fname}: {e}")
                continue
        else:
            # ignore unknown file types
            continue

        if txt.strip():
            texts.append({"source": fname, "text": txt, "category": None, "url": None})
    return texts

def build_vectorstore(ref_dir='adgm_docs', persist_directory='chroma_db'):
    """
    Build a Chroma vectorstore from the files in ref_dir.
    Requires GOOGLE_API_KEY environment variable to be set for GoogleGenerativeAIEmbeddings.
    """
    if not os.path.exists(ref_dir):
        raise FileNotFoundError(
            f"Reference directory '{ref_dir}' not found. Please create it and add ADGM docs."
        )

    texts = load_reference_texts(ref_dir)
    docs = []
    # legal documents: smaller chunk size and more overlap helps context
    splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=180)

    for t in texts:
        chunks = splitter.split_text(t['text'])
        for i, chunk in enumerate(chunks):
            docs.append(LangDoc(
                page_content=chunk,
                metadata={
                    "source": t['source'],
                    "chunk": i,
                    "category": t.get('category'),
                    "url": t.get('url')
                }
            ))

    if not docs:
        raise ValueError(
            "No text found in reference documents. Ensure adgm_docs contains valid .pdf, .txt, or .docx files."
        )

    # Ensure the Google API key is set (used by the embeddings)
    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
        raise EnvironmentError(
            "GOOGLE_API_KEY (or GEMINI_API_KEY) environment variable not set. Please set it before running."
        )

    # Use Google/Gemini embeddings if available
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    vectordb = Chroma.from_documents(docs, embeddings, persist_directory=persist_directory)
    vectordb.persist()
    print("Built Chroma vectorstore with Gemini embeddings and persisted to", persist_directory)
    return vectordb

def load_vectorstore(persist_directory='chroma_db'):
    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
        raise EnvironmentError(
            "GOOGLE_API_KEY (or GEMINI_API_KEY) environment variable not set. Please set it before running."
        )
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    vectordb = Chroma(
        persist_directory=persist_directory,
        embedding_function=embeddings
    )
    return vectordb

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', action='store_true', help='Build vectorstore from files in adgm_docs/')
    parser.add_argument('--refdir', default='adgm_docs')
    parser.add_argument('--persist', default='chroma_db')
    args = parser.parse_args()

    if args.build:
        build_vectorstore(ref_dir=args.refdir, persist_directory=args.persist)
    else:
        print('Use --build to construct a vectorstore from adgm_docs/')
