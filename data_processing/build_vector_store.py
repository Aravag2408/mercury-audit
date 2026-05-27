from sentence_transformers import SentenceTransformer
import faiss, json, numpy as np, pickle

with open('../data/rag_chunks.json') as f:
    doc_chunks = json.load(f)

with open('../data/patient_records.json') as f:
    patients = json.load(f)

for p in patients:
    doc_chunks.append({
        "source": "patient_records",
        "text": json.dumps(p),
        "patient_id": p['patient_id']
    })

print(f"Total documents to embed: {len(doc_chunks)}")

model = SentenceTransformer('all-MiniLM-L6-v2')
texts = [c['text'] for c in doc_chunks]
embeddings = model.encode(texts, show_progress_bar=True)

dimension = embeddings.shape[1]
index = faiss.IndexFlatL2(dimension)
index.add(np.array(embeddings).astype('float32'))

faiss.write_index(index, '../data/faiss_index.bin')
with open('../data/faiss_metadata.pkl', 'wb') as f:
    pickle.dump(doc_chunks, f)

print(f"Vector store built with {len(doc_chunks)} documents")
print("Saved: data/faiss_index.bin, data/faiss_metadata.pkl")
