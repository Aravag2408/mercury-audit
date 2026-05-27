# Mercury — Complete Setup Guide

## Prerequisites (install once)
- **VS Code** — https://code.visualstudio.com/
- **Claude Code extension** — install from VS Code Extensions marketplace (search "Claude Code")
- **Python 3.10+** — https://www.python.org/downloads/
- **Java 11+** — required for Synthea — https://adoptium.net/
- **Git** — https://git-scm.com/

---

## Phase 1 — Project Setup in VS Code

### 1.1 Create your project folder
```bash
mkdir mercury-audit
cd mercury-audit
```

### 1.2 Clone the ruslanmv repo
```bash
git clone https://github.com/ruslanmv/ai-medical-chatbot.git
```

### 1.3 Clone Synthea
```bash
git clone https://github.com/synthetichealth/synthea.git
```

### 1.4 Open in VS Code
```bash
code .
```

Your folder structure should now look like:
```
mercury-audit/
├── ai-medical-chatbot/
│   ├── 2-Data/
│   ├── 3-Modeling/
│   ├── 6-FineTunning/
│   ├── 9-HuggingFace-Global/
│   └── web/
└── synthea/
```

### 1.5 Create a Python virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### 1.6 Install base dependencies
```bash
pip install datasets pandas transformers torch huggingface_hub langchain faiss-cpu sentence-transformers PyPDF2
```

---

## Phase 2 — Generate Patient Data (Synthea)

### 2.1 Build Synthea
```bash
cd synthea
./gradlew build -x test         # Mac/Linux
gradlew.bat build -x test       # Windows
```

### 2.2 Run Synthea with STD-relevant conditions
Synthea generates patients by condition. Run it for the STDs Mercury handles:
```bash
# Generate 200 patients with STD conditions
./run_synthea -p 200 \
  --exporter.fhir.export=false \
  --exporter.csv.export=true \
  "chlamydia" "gonorrhea" "syphilis" "HIV" "herpes"
```
Output lands in `synthea/output/csv/`

### 2.3 Key output files you need
- `patients.csv` — patient demographics (name, DOB, ID, address)
- `conditions.csv` — diagnoses per patient
- `medications.csv` — treatments per patient
- `observations.csv` — lab results (HIV status etc.)

### 2.4 Convert Synthea output to Mercury patient records
Create `mercury-audit/data_processing/build_patient_records.py`:

```python
import pandas as pd
import json

# Load Synthea CSVs
patients = pd.read_csv('../synthea/output/csv/patients.csv')
conditions = pd.read_csv('../synthea/output/csv/conditions.csv')
medications = pd.read_csv('../synthea/output/csv/medications.csv')

# STD-relevant ICD codes to keep
STD_CODES = [
    'A56',   # Chlamydia
    'A54',   # Gonorrhea  
    'A51', 'A52', 'A53',  # Syphilis
    'B20',   # HIV
    'A60',   # Herpes
    'B97.7', # HPV
]

# Filter to STD patients only
std_conditions = conditions[
    conditions['CODE'].astype(str).str.startswith(tuple(STD_CODES))
]
std_patient_ids = std_conditions['PATIENT'].unique()
std_patients = patients[patients['Id'].isin(std_patient_ids)]

# Build patient record JSON (Mercury format)
records = []
for _, patient in std_patients.iterrows():
    pid = patient['Id']
    pt_conditions = std_conditions[std_conditions['PATIENT'] == pid]
    pt_meds = medications[medications['PATIENT'] == pid]
    
    record = {
        "patient_id": f"AFIK-{str(pid)[:5].upper()}",
        "full_name": f"{patient['FIRST']} {patient['LAST']}",
        "dob": patient['BIRTHDATE'],
        "address": patient['ADDRESS'],
        "city": patient['CITY'],
        "diagnoses": pt_conditions['DESCRIPTION'].tolist(),
        "medications": pt_meds['DESCRIPTION'].tolist(),
        "hiv_status": "Positive" if any(
            str(c).startswith('B20') for c in pt_conditions['CODE']
        ) else "Negative"
    }
    records.append(record)

# Save
with open('../data/patient_records.json', 'w') as f:
    json.dump(records, f, indent=2)

print(f"Generated {len(records)} STD patient records")
```

Run it:
```bash
mkdir -p mercury-audit/data
python mercury-audit/data_processing/build_patient_records.py
```

---

## Phase 3 — Prepare Conversation Data (Fine-tuning)

### 3.1 Filter ruslanmv dataset for STD entries
Create `mercury-audit/data_processing/filter_conversations.py`:

```python
from datasets import load_dataset
import pandas as pd

# Load the full dataset
print("Loading dataset...")
dataset = load_dataset("ruslanmv/ai-medical-chatbot", split="train")
df = dataset.to_pandas()

# STD keywords to filter on
STD_KEYWORDS = [
    'chlamydia', 'gonorrhea', 'gonorrhoea', 'syphilis',
    'HIV', 'herpes', 'HPV', 'genital warts', 'STD', 'STI',
    'sexually transmitted', 'trichomoniasis', 'discharge',
    'urethritis', 'cervicitis', 'PrEP', 'antiretroviral'
]

# Filter rows where Description contains any keyword (case-insensitive)
pattern = '|'.join(STD_KEYWORDS)
std_df = df[df['Description'].str.contains(pattern, case=False, na=False)]

print(f"Found {len(std_df)} STD-relevant conversations out of {len(df)}")

# Save in fine-tuning format
std_df[['Description', 'Doctor']].to_csv(
    '../data/std_conversations.csv', index=False
)
print("Saved to data/std_conversations.csv")
```

Run it:
```bash
python mercury-audit/data_processing/filter_conversations.py
```

---

## Phase 4 — Prepare RAG Corpus (Clinical Reference Docs)

### 4.1 Download the PDFs
```bash
mkdir -p mercury-audit/data/rag_docs

# CDC Guidelines
curl -o mercury-audit/data/rag_docs/cdc_sti_guidelines_2021.pdf \
  "https://www.cdc.gov/std/treatment-guidelines/STI-Guidelines-2021.pdf"

# WHO Guidelines
curl -o mercury-audit/data/rag_docs/who_sti_guidelines.pdf \
  "https://iris.who.int/server/api/core/bitstreams/d5869a37-9b00-4ce9-9111-b4b3f1c19b30/content"
```

### 4.2 Chunk PDFs into RAG-ready text
Create `mercury-audit/data_processing/chunk_pdfs.py`:

```python
from langchain.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
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
```

Run it:
```bash
python mercury-audit/data_processing/chunk_pdfs.py
```

---

## Phase 5 — Fine-tune the Model (Colab for GPU)

For this step only, use Google Colab because it needs a GPU.

### 5.1 Open the ruslanmv fine-tuning notebook
Go to: `ai-medical-chatbot/6-FineTunning/`
Open the Llama3 fine-tuning notebook in Colab.

### 5.2 Point it at your STD data instead of the full dataset
In the notebook, replace the dataset loading cell with:
```python
import pandas as pd
from datasets import Dataset

df = pd.read_csv('std_conversations.csv')  # upload this to Colab
dataset = Dataset.from_pandas(df)
```

### 5.3 Run the notebook
Follow the notebook instructions. When done, download the fine-tuned model weights and save them in:
```
mercury-audit/models/mercury-llm/
```

---

## Phase 6 — Build the RAG Vector Store

### 6.1 Index everything into FAISS
Create `mercury-audit/data_processing/build_vector_store.py`:

```python
from sentence_transformers import SentenceTransformer
import faiss, json, numpy as np, pickle

# Load chunks (PDFs + patient records)
with open('../data/rag_chunks.json') as f:
    doc_chunks = json.load(f)

with open('../data/patient_records.json') as f:
    patients = json.load(f)

# Add patient records as chunks too
for p in patients:
    doc_chunks.append({
        "source": "patient_records",
        "text": json.dumps(p),
        "patient_id": p['patient_id']
    })

# Embed everything
print("Embedding documents...")
model = SentenceTransformer('all-MiniLM-L6-v2')
texts = [c['text'] for c in doc_chunks]
embeddings = model.encode(texts, show_progress_bar=True)

# Build FAISS index
dimension = embeddings.shape[1]
index = faiss.IndexFlatL2(dimension)
index.add(np.array(embeddings).astype('float32'))

# Save index and metadata
faiss.write_index(index, '../data/faiss_index.bin')
with open('../data/faiss_metadata.pkl', 'wb') as f:
    pickle.dump(doc_chunks, f)

print(f"Vector store built with {len(doc_chunks)} documents")
```

Run it:
```bash
python mercury-audit/data_processing/build_vector_store.py
```

---

## Phase 7 — Wire It Together

At this point you have:
- Fine-tuned model weights in `models/mercury-llm/`
- FAISS index in `data/faiss_index.bin`
- Patient records in `data/patient_records.json`

Now open the ruslanmv `9-HuggingFace-Global/` backend folder and point it at your model and your FAISS index. Claude Code will help you with the specific file edits needed here — this is where having it open in VS Code pays off.

---

## Final Folder Structure
```
mercury-audit/
├── ai-medical-chatbot/        # ruslanmv repo (base system)
├── synthea/                   # patient data generator
├── data/
│   ├── patient_records.json   # Synthea output, reformatted
│   ├── std_conversations.csv  # filtered fine-tuning data
│   ├── rag_docs/              # CDC + WHO PDFs
│   ├── rag_chunks.json        # chunked PDF text
│   ├── faiss_index.bin        # vector store
│   └── faiss_metadata.pkl     # chunk metadata
├── models/
│   └── mercury-llm/           # fine-tuned model weights
└── data_processing/
    ├── build_patient_records.py
    ├── filter_conversations.py
    ├── chunk_pdfs.py
    └── build_vector_store.py
```

---

## Notes
- Phases 1–4 and 6–7: do in VS Code with Claude Code
- Phase 5 (fine-tuning): do in Google Colab (needs GPU)
- Claude Code is most useful in Phase 7 when wiring the pieces together
