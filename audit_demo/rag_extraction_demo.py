"""
rag_extraction_demo.py — Mercury RAG Privacy Audit Demo

Demonstrates that a signed-in Mercury user, through normal chatbot use,
triggers retrieval of real patient-authored text from the RAG corpus —
text written by third parties who never consented to appear in this system.

SUBJECT: Privacy and Memorization in Large Language Models
FINDING:  RAG is verbatim memorization. Unlike weight memorization (probabilistic),
          RAG stores source text exactly and retrieves it on demand.
          Any query that keyword-matches a real patient's question surfaces
          that patient's words into a different user's chat session.

SOURCE DATA: ruslanmv/ai-medical-chatbot → HealthCareMagic (real patient Q&A platform)
             Patients typed intimate medical questions to get doctor advice.
             They did not consent to appearing in an AI chatbot's corpus.

USAGE:
    cd mercury-audit/audit_demo
    python rag_extraction_demo.py
    python rag_extraction_demo.py --query "discharge from penis when touched"
    python rag_extraction_demo.py --list-identifying   # show all PII-bearing chunks
"""

import json
import re
import argparse
import os

RAG_CHUNKS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'rag_chunks.json')

# ── Exact replica of medical-kb.ts scoring logic ─────────────────────────────

STOP_WORD_MIN_LEN = 4  # words shorter than 4 chars are skipped (mirrors JS code)

def score_chunk(text: str, query_words: list[str]) -> int:
    text_lower = text.lower()
    score = 0
    for word in query_words:
        if len(word) < STOP_WORD_MIN_LEN:
            continue
        if word in text_lower:
            score += len(word)
    return score

def search_rag(query: str, chunks: list[dict], top_n: int = 3) -> list[dict]:
    query_words = query.lower().split()
    scored = [
        (score_chunk(c['text'], query_words), i, c)
        for i, c in enumerate(chunks)
        if score_chunk(c['text'], query_words) > 0
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{'score': s, 'chunk': c} for s, _, c in scored[:top_n]]

# ── PII detection (same patterns used in earlier analysis) ────────────────────

PII_PATTERNS = [
    r'\bI am a \d{1,2}',
    r'\bI am \d{1,2}',
    r'\bmy (husband|wife|boyfriend|girlfriend|partner)\b',
    r'\bI have been (diagnosed|tested|positive)\b',
    r'\b\d{1,2} year[s]? old (male|female|man|woman|girl|boy)\b',
    r'\bmy (doctor|gynecologist|urologist)\b',
]

def has_pii(text: str) -> bool:
    question_part = text.split('Doctor answer:')[0]
    return any(re.search(p, question_part, re.I) for p in PII_PATTERNS)

# ── Display helpers ───────────────────────────────────────────────────────────

SEPARATOR = '─' * 70

def print_chunk(rank: int, result: dict):
    chunk = result['chunk']
    score = result['score']
    source = chunk.get('source', 'unknown')
    text = chunk['text']
    pii_flag = '  ⚠  CONTAINS PATIENT-IDENTIFYING DETAIL' if has_pii(text) else ''

    print(f'\n{SEPARATOR}')
    print(f'  Rank #{rank}  |  score={score}  |  source={source}{pii_flag}')
    print(SEPARATOR)
    print(text[:800])
    if len(text) > 800:
        print(f'  ... [{len(text) - 800} more chars]')

def build_injected_context(results: list[dict]) -> str:
    """Reproduce exactly what medical-kb.ts injects into the LLM prompt."""
    if not results:
        return ''
    parts = []
    for r in results:
        source = r['chunk'].get('source', 'unknown').replace('_', ' ').replace('.pdf', '')
        parts.append(f"[{source}]: {r['chunk']['text']}")
    context = '\n\n'.join(parts)
    return (
        '\n\nRelevant medical knowledge:\n'
        + context
        + '\n\nUse the above medical knowledge to inform your response, '
          'but always use your general medical training as well. '
          'Do not simply copy the context — synthesize it into a helpful, '
          'conversational response.'
    )

# ── Main demo modes ───────────────────────────────────────────────────────────

def demo_query(chunks: list[dict], query: str):
    print(f'\n{"=" * 70}')
    print('  MERCURY RAG PRIVACY AUDIT — RETRIEVAL DEMO')
    print(f'{"=" * 70}')
    print(f'\n  User query (signed-in patient): "{query}"')
    print(f'  Total corpus size: {len(chunks):,} chunks\n')

    results = search_rag(query, chunks, top_n=3)

    if not results:
        print('  No chunks retrieved for this query.')
        return

    print(f'  Top {len(results)} chunks retrieved and injected into LLM context:')

    pii_count = 0
    for i, r in enumerate(results, 1):
        print_chunk(i, r)
        if has_pii(r['chunk']['text']):
            pii_count += 1

    print(f'\n{SEPARATOR}')
    print('  WHAT THE LLM ACTUALLY RECEIVES (injected context block):')
    print(SEPARATOR)
    injected = build_injected_context(results)
    print(injected[:1500])
    if len(injected) > 1500:
        print(f'  ... [{len(injected) - 1500} more chars]')

    print(f'\n{SEPARATOR}')
    print('  AUDIT FINDING SUMMARY')
    print(SEPARATOR)
    print(f'  Query matched {len(results)} chunks from the corpus.')
    print(f'  {pii_count} of those chunks contain patient-identifying detail.')
    if pii_count > 0:
        print()
        print('  A real patient\'s intimate medical question — written on HealthCareMagic,')
        print('  a third-party medical platform — has been retrieved verbatim and injected')
        print('  into this user\'s LLM session without that patient\'s knowledge or consent.')
        print()
        print('  Authentication status: irrelevant. Signed-in and guest users are equally')
        print('  affected. RAG retrieval runs before authentication is checked.')
    print()


def list_identifying_chunks(chunks: list[dict]):
    """Print all chunks with patient-identifying detail."""
    conv = [c for c in chunks if 'conversation' in c.get('source', '') or 'qa' in c.get('source', '')]
    hits = [c for c in conv if has_pii(c['text'])]

    print(f'\n  Found {len(hits)} patient-identifying chunks out of {len(conv):,} conversation chunks')
    print(f'  (and {len(chunks) - len(conv):,} clinical guideline chunks)\n')

    for i, c in enumerate(hits, 1):
        q_part = c['text'].split('Doctor answer:')[0].strip()
        print(f'  [{i:02d}] {q_part[:120]}')
    print()


def main():
    parser = argparse.ArgumentParser(description='Mercury RAG privacy audit demo')
    parser.add_argument('--query', type=str,
                        default='I have discharge from my penis when my partner touches me',
                        help='Simulated user query')
    parser.add_argument('--list-identifying', action='store_true',
                        help='List all PII-bearing chunks in the corpus')
    args = parser.parse_args()

    if not os.path.exists(RAG_CHUNKS_PATH):
        print(f'\n  ERROR: {RAG_CHUNKS_PATH} not found.')
        print('  Run data_processing/build_rag.py first.\n')
        return

    print(f'  Loading corpus from {RAG_CHUNKS_PATH}...')
    chunks = json.load(open(RAG_CHUNKS_PATH, encoding='utf-8'))

    if args.list_identifying:
        list_identifying_chunks(chunks)
    else:
        demo_query(chunks, args.query)


if __name__ == '__main__':
    main()
