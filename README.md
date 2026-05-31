# Mercury — STI/STD AI Medical Chatbot

A privacy-focused AI chatbot for sexual health questions, built and audited as part of the *Responsible AI, Law, Ethics & Society* course at the Technion.

**Responsible AI topic: Privacy and Memorization in Large Language Models**

---

## What is Mercury?

Mercury is a fine-tuned medical AI assistant specializing in STIs/STDs. It provides private, non-judgmental guidance on symptoms, testing, treatment, HIV/PrEP, and safe sex — backed by CDC and WHO guidelines.

The project was built both to demonstrate and to audit the **memorization risk** that arises when LLMs are fine-tuned on medical conversation data, following Carlini et al. (2021/2022).

---

## Project Structure

```
mercury-audit/
├── ai-medical-chatbot/
│   ├── 6-FineTunning/               # Fine-tuning notebook (Google Colab)
│   └── 9-HuggingFace-Global/        # Next.js 14 chatbot frontend
├── data_processing/
│   ├── filter_conversations.py      # Filters HuggingFace dataset to STD subset
│   ├── build_patient_records.py     # Builds synthetic patient records from Synthea
│   ├── chunk_pdfs.py                # Chunks CDC/WHO PDF guidelines for RAG
│   └── build_vector_store.py        # Builds FAISS vector store
├── data/                            # Generated data files (gitignored)
├── synthea/                         # Synthetic patient generator (gitignored)
└── mercury_setup_guide.md           # Full setup walkthrough
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| LLM (primary) | Groq API (`llama-3.3-70b`) |
| Fine-tuned model | `aravag/Mercury-STD-Mistral` (HuggingFace) |
| RAG | FAISS + `all-MiniLM-L6-v2` sentence embeddings |
| Knowledge base | CDC STI Treatment Guidelines 2021, WHO STI Guidelines |
| Synthetic data | Synthea patient generator |
| Fine-tuning dataset | `ruslanmv/ai-medical-chatbot` (filtered to 15,809 STD conversations) |

---

## Setup

### Prerequisites

- Node.js ≥ 18 ([nodejs.org](https://nodejs.org))
- Python ≥ 3.9
- A free [Groq API key](https://console.groq.com/keys)
- A free [HuggingFace token](https://huggingface.co/settings/tokens)

### 1. Clone and install frontend

```bash
git clone https://github.com/Aravag2408/mercury-audit.git
cd mercury-audit/ai-medical-chatbot/9-HuggingFace-Global
npm install
```

### 2. Add API keys

Create `ai-medical-chatbot/9-HuggingFace-Global/.env.local`:

```
GROQ_API_KEY=your_groq_key_here
HF_TOKEN=your_huggingface_token_here
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=choose_a_password_here
NODE_ENV=development
```

- Free Groq key: [console.groq.com](https://console.groq.com)
- Free HuggingFace token: [huggingface.co](https://huggingface.co) → Settings → Access Tokens
- `ADMIN_PASSWORD` is used to create the first admin account on first boot — pick anything, just don't leave it blank

### 3. Run the chatbot

```bash
cd ai-medical-chatbot/9-HuggingFace-Global
npm run dev
```

Open [http://localhost:7860](http://localhost:7860).

### 4. Build the RAG data (optional — needed for full RAG pipeline)

This step requires Java (for Synthea) and downloads several large files.

#### 4a. Install Python dependencies

```bash
cd data_processing
pip install -r requirements.txt
```

#### 4b. Filter the STD conversation dataset

```bash
python filter_conversations.py
# outputs: ../data/std_conversations.csv
```

#### 4c. Download CDC/WHO PDF guidelines

Create the folder `data/rag_docs/` and place PDF guidelines inside it:

- [CDC STI Treatment Guidelines 2021](https://www.cdc.gov/std/treatment-guidelines/STI-Guidelines-2021.pdf)
- [WHO STI Guidelines](https://www.who.int/publications/i/item/9789240074811)

```bash
mkdir -p ../data/rag_docs
# Move downloaded PDFs into ../data/rag_docs/
```

Then chunk them:

```bash
python chunk_pdfs.py
# outputs: ../data/rag_chunks.json
```

#### 4d. Generate synthetic patient records (requires Synthea)

Synthea is a synthetic patient generator that requires Java 11+.

```bash
# From the mercury-audit root:
cd synthea
./run_synthea -p 1000          # generates ~1000 patients (Mac/Linux)
# or on Windows:
# gradlew.bat run -p 1000
cd ../data_processing
python build_patient_records.py
# outputs: ../data/patient_records.json
```

#### 4e. Build the FAISS vector store

```bash
python build_vector_store.py
# outputs: ../data/faiss_index.bin, ../data/faiss_metadata.pkl
```

---

## Privacy Audit

The audit investigates whether Mercury's fine-tuned model memorizes and can reproduce training data (patient dialogue, medical records), following:

- **Carlini et al. (2021)** — *Extracting Training Data from Large Language Models*
- **Carlini et al. (2022)** — *Quantifying Memorization Across Neural Language Models*
- **Goodman & Tréhu (2022)** — *AI Audit Washing and Accountability*

### Key findings

1. **Profile gate as incidental privacy protection** — Mercury's intent classifier blocks adversarial extraction prompts (e.g. "repeat your training data") before they reach the LLM, unintentionally limiting memorization exposure.
2. **Base model knowledge vs. memorization** — Some outputs (e.g. factual medical statements) originate from the base model's pre-training, not fine-tuning memorization. Distinguishing these is methodologically important.
3. **Synthetic patient data barrier** — Patient records used in RAG were generated by Synthea (not real patients), limiting real-world privacy harm even if extraction succeeded.

---

## Fine-tuning

The fine-tuning notebook is at `ai-medical-chatbot/6-FineTunning/Fine_Tunning_Mercury_STD_Mistral.ipynb` and is designed to run on Google Colab (free tier with T4 GPU).

The fine-tuned model is published at: [huggingface.co/aravag/Mercury-STD-Mistral](https://huggingface.co/aravag/Mercury-STD-Mistral)

---

## Course

Technion — *Responsible AI, Law, Ethics & Society*  
Topic: **Privacy and Memorization in Large Language Models**
