from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import json, os

PDF_DIR = "../data/rag_docs"
OUTPUT = "../data/rag_chunks.json"

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50
)

all_chunks = []
for filename in os.listdir(PDF_DIR):
    if filename.endswith('.pdf'):
        loader = PyPDFLoader(os.path.join(PDF_DIR, filename))
        pages = loader.load()
        chunks = splitter.split_documents(pages)
        for chunk in chunks:
            all_chunks.append({
                "source": filename,
                "text": chunk.page_content
            })
        print(f"{filename}: {len(chunks)} chunks")

with open(OUTPUT, 'w') as f:
    json.dump(all_chunks, f, indent=2)

print(f"Total chunks: {len(all_chunks)}")
