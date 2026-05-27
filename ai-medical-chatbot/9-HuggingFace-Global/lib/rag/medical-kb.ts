/**
 * Medical Knowledge Base for RAG.
 * Loads CDC/WHO STI guideline chunks from rag_chunks.json (built by
 * data_processing/chunk_pdfs.py) and searches them by keyword overlap.
 *
 * The chunks live in the repo at data/rag_chunks.json (2 823 entries).
 * They are read once at module load and cached for the process lifetime.
 */

import fs from 'fs';
import path from 'path';

interface RagChunk {
  source: string;
  text: string;
  patient_id?: string;
}

interface ScoredChunk {
  chunk: RagChunk;
  score: number;
}

// Resolve relative to the repo root regardless of where Next.js runs from.
const RAG_CHUNKS_PATH = path.resolve(process.cwd(), '../../data/rag_chunks.json');

let _chunks: RagChunk[] | null = null;

function loadChunks(): RagChunk[] {
  if (_chunks) return _chunks;
  try {
    const raw = fs.readFileSync(RAG_CHUNKS_PATH, 'utf-8');
    _chunks = JSON.parse(raw) as RagChunk[];
    console.log(`[RAG] Loaded ${_chunks.length} chunks from ${RAG_CHUNKS_PATH}`);
  } catch (err) {
    console.warn(`[RAG] Could not load rag_chunks.json: ${err}. Falling back to empty corpus.`);
    _chunks = [];
  }
  return _chunks;
}

/**
 * Score a chunk against a query using word-overlap.
 * Longer matching words score higher; stop-words (<4 chars) are skipped.
 */
function scoreChunk(chunk: RagChunk, queryWords: string[]): number {
  const text = chunk.text.toLowerCase();
  let score = 0;
  for (const word of queryWords) {
    if (word.length < 4) continue;
    if (text.includes(word)) {
      score += word.length;
    }
  }
  return score;
}

export function searchMedicalKB(query: string, topN: number = 3): { topic: string; context: string }[] {
  const chunks = loadChunks();
  if (chunks.length === 0) return [];

  const queryWords = query.toLowerCase().split(/\s+/);

  const scored: ScoredChunk[] = chunks
    .map((chunk) => ({ chunk, score: scoreChunk(chunk, queryWords) }))
    .filter((s) => s.score > 0);

  scored.sort((a, b) => b.score - a.score);

  return scored.slice(0, topN).map((s) => ({
    topic: s.chunk.source.replace(/_/g, ' ').replace('.pdf', ''),
    context: s.chunk.text,
  }));
}

export function buildRAGContext(query: string): string {
  const results = searchMedicalKB(query);
  if (results.length === 0) return '';

  const context = results
    .map((r) => `[${r.topic}]: ${r.context}`)
    .join('\n\n');

  return `\n\nRelevant medical knowledge:\n${context}\n\nUse the above medical knowledge to inform your response, but always use your general medical training as well. Do not simply copy the context — synthesize it into a helpful, conversational response.`;
}
