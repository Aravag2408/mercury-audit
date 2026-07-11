/**
 * Storage-layer PII scrub for the live RAG corpus.
 *
 * Runs between a chat turn and `addUserConversationChunk` when the
 * MEDOS_RAG_SCRUB flag is on. Two stages:
 *   1. Regex floor (deterministic): structured PII → typed placeholders.
 *      Same regex-first style as lib/safety/output-filter.ts.
 *   2. LLM de-identification rewrite: collapses the turn into a short,
 *      de-identified clinical summary via the existing provider fallback
 *      chain, stripping free-text identifiers (names, workplaces, clinic
 *      names, exact age, location) that regex cannot see.
 *
 * FAIL-CLOSED: if the LLM stage cannot complete (all providers down, or an
 * empty completion), `scrubForStorage` throws. The caller
 * (`addUserConversationChunk`) drops the turn rather than store anything
 * that was not fully de-identified.
 */

import { chatWithFallback, type ChatMessage } from '@/lib/providers';

/**
 * Stage 1 — deterministic structured-PII patterns, applied in order.
 * Email is first so digits in a local-part aren't eaten by a numeric rule;
 * the 9-digit national-ID rule precedes the phone rule so a bare Israeli ID
 * (e.g. "031456789") is tagged [ID] rather than [PHONE].
 */
const STRUCTURED_PII: Array<[RegExp, string]> = [
  // Email addresses.
  [/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, '[EMAIL]'],
  // Israeli national ID: exactly 9 digits standing alone.
  [/\b\d{9}\b/g, '[ID]'],
  // Phone numbers: +972 / 0-prefixed Israeli mobile & landline, with
  // optional space/hyphen separators.
  [/(?:\+972|0)[-\s]?(?:\d[-\s]?){7,9}\d/g, '[PHONE]'],
  // Dates (DOB, test dates): dd/mm/yyyy, dd.mm.yyyy, dd-mm-yyyy, yyyy-mm-dd.
  [/\b(?:\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2})\b/g, '[DATE]'],
];

/** Replace structured PII with typed placeholders. Deterministic, offline. */
export function regexScrub(text: string): string {
  let out = text;
  for (const [rx, tag] of STRUCTURED_PII) {
    out = out.replace(rx, tag);
  }
  return out;
}

const DEID_SYSTEM_PROMPT = `You are a clinical data de-identification filter. You receive one patient chat turn (a patient message and the assistant's reply). Rewrite it as a SHORT de-identified clinical summary suitable for storage.

REMOVE every direct or indirect identifier:
- personal names (patient, partners, friends, doctors) — keep no names at all
- workplaces, employers, schools, universities, military units
- clinic, hospital, health-fund, and laboratory names
- cities, neighbourhoods, streets, venues, festivals, countries
- exact ages (use a decade band such as "20s"), dates, ID numbers, phone numbers, emails

KEEP the clinically useful signal:
- symptom pattern and timeline
- test, diagnosis, and treatment in generic terms (e.g. "PEP", "a penicillin injection")
- emotional tone (anxious, relieved, angry)

Output ONLY the rewritten summary as 1-3 plain sentences. No preamble, no names, no place names, no bracketed placeholders, no lists.`;

/**
 * De-identify one conversation turn before it enters the live RAG corpus.
 * Returns the de-identified summary text. Throws (fail-closed) if the LLM
 * de-identification stage cannot complete.
 */
export async function scrubForStorage(
  userMessage: string,
  assistantResponse: string,
): Promise<string> {
  // Stage 1 — deterministic structured-PII floor.
  const preUser = regexScrub(userMessage);
  const preAssistant = regexScrub(assistantResponse);

  // Stage 2 — LLM de-identification rewrite of the combined turn.
  const messages: ChatMessage[] = [
    { role: 'system', content: DEID_SYSTEM_PROMPT },
    {
      role: 'user',
      content: `Patient message: ${preUser}\nAssistant reply: ${preAssistant}`,
    },
  ];

  // Throws AllProvidersUnavailableError if every provider fails.
  const resp = await chatWithFallback(messages);
  const summary = (resp.content || '').trim();
  if (!summary) {
    throw new Error('scrubForStorage: empty de-identification output');
  }

  // Defense in depth: re-run the regex floor in case the model echoed a
  // structured identifier from the input.
  return regexScrub(summary);
}
