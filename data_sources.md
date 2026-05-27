# Mercury Audit — Data Sources

## System Being Built (Mercury's Base)
- **ruslanmv/ai-medical-chatbot** — https://github.com/ruslanmv/ai-medical-chatbot

## Academic Justification for System Design
- **SARHAchat** (UNC School of Nursing, arXiv Oct 2025) — https://arxiv.org/abs/2510.16081

---

## Data Sources

| Layer | Source | Link |
|---|---|---|
| Conversation data (fine-tuning) | ruslanmv HuggingFace dataset, filtered for STD entries | https://huggingface.co/datasets/ruslanmv/ai-medical-chatbot |
| Patient records | Synthea by MITRE | https://github.com/synthetichealth/synthea |
| Clinical reference (RAG corpus) | CDC STI Treatment Guidelines 2021 PDF | https://www.cdc.gov/std/treatment-guidelines/STI-Guidelines-2021.pdf |
| Clinical reference (RAG corpus) | WHO Guidelines for Management of Symptomatic STIs PDF | https://iris.who.int/server/api/core/bitstreams/d5869a37-9b00-4ce9-9111-b4b3f1c19b30/content |
