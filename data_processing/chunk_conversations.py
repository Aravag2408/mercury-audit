import pandas as pd
import json
import os

CONVERSATIONS_PATH = '../data/std_conversations.csv'
RAG_CHUNKS_PATH = '../data/rag_chunks.json'

df = pd.read_csv(CONVERSATIONS_PATH)
print(f"Loaded {len(df)} STD conversations")

# Load existing chunks (from chunk_pdfs.py) and append to them
existing_chunks = []
if os.path.exists(RAG_CHUNKS_PATH):
    with open(RAG_CHUNKS_PATH) as f:
        existing_chunks = json.load(f)
    print(f"Found {len(existing_chunks)} existing chunks (PDFs)")

conversation_chunks = []
for _, row in df.iterrows():
    question = str(row.get('Description', '')).strip()
    answer = str(row.get('Doctor', '')).strip()
    if not question or not answer:
        continue
    conversation_chunks.append({
        "source": "doctor_patient_conversation",
        "text": f"Patient: {question}\nDoctor: {answer}"
    })

all_chunks = existing_chunks + conversation_chunks

with open(RAG_CHUNKS_PATH, 'w') as f:
    json.dump(all_chunks, f, indent=2)

print(f"Added {len(conversation_chunks)} conversation chunks")
print(f"Total RAG corpus: {len(all_chunks)} chunks -> {RAG_CHUNKS_PATH}")
