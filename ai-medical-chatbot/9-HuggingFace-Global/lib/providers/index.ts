import {
  streamWithOllaBridge,
  chatWithOllaBridge,
  isOllaBridgeConfigured,
} from './ollabridge';
import {
  streamWithHuggingFace,
  chatWithHuggingFace,
} from './huggingface-direct';
import {
  streamWithGroq,
  chatWithGroq,
  isGroqConfigured,
} from './groq';
import {
  streamWithOpenRouter,
  chatWithOpenRouter,
  isOpenRouterConfigured,
} from './openrouter';
import {
  streamWithGemini,
  chatWithGemini,
  isGeminiConfigured,
} from './gemini';

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface ProviderResponse {
  content: string;
  provider: string;
  model: string;
}

/**
 * Thrown when every configured LLM provider fails for a request. The
 * chat route translates this into a user-facing "service unavailable"
 * SSE error event. We do NOT fall back to a canned response: a
 * keyword-matched dictionary that speaks in the voice of a medical AI
 * is worse than no answer at all — users assume it came from the
 * model and act on it.
 */
export class AllProvidersUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AllProvidersUnavailableError';
  }
}

/**
 * Structured logger that prefixes every line with `[Chat]` so the HF Space
 * logs API can be grepped for a single request end-to-end.
 */
function log(stage: string, details?: Record<string, unknown>) {
  const payload = details ? ` ${JSON.stringify(details)}` : '';
  console.log(`[Chat] ${stage}${payload}`);
}

/**
 * Stream chat completion with automatic fallback chain:
 *   1. Groq Cloud (llama-3.3-70b-versatile) — primary.
 *   2. Gemini 2.0 Flash — fallback when Groq is rate-limited (1500 req/day free).
 *   3. OpenRouter (llama-3.1-8b-instruct:free) — second fallback.
 *   4. OllaBridge-Cloud — only if admin has set OLLABRIDGE_URL.
 *   5. HuggingFace Inference API — cascades through model chain including
 *      Mercury-STD-Mistral as last resort.
 *
 * If every provider fails, throws AllProvidersUnavailableError. There is
 * intentionally NO "cached FAQ" fallback: a keyword dictionary speaking
 * in the voice of a medical AI is worse than an honest error.
 *
 * Each step logs its decision so the workflow can be traced from the
 * HF Space run logs.
 */
export async function streamWithFallback(
  messages: ChatMessage[],
  model: string = 'qwen2.5:1.5b'
): Promise<ReadableStream> {
  const requestId = Math.random().toString(36).slice(2, 10);
  const startedAt = Date.now();
  const userTurn = messages.filter((m) => m.role === 'user').pop();
  log('request.start', {
    requestId,
    model,
    turns: messages.length,
    userChars: userTurn?.content.length ?? 0,
  });

  const failures: string[] = [];

  // Step 1 — Groq (primary).
  if (isGroqConfigured()) {
    const tg = Date.now();
    try {
      const stream = await streamWithGroq(messages, model);
      log('provider.groq.ok', {
        requestId,
        latencyMs: Date.now() - tg,
        totalMs: Date.now() - startedAt,
      });
      return stream;
    } catch (error: any) {
      const msg = String(error?.message || error).slice(0, 200);
      log('provider.groq.fail', {
        requestId,
        latencyMs: Date.now() - tg,
        error: msg,
      });
      failures.push(`groq: ${msg}`);
    }
  } else {
    log('provider.groq.skipped', { requestId, reason: 'not configured' });
  }

  // Step 2 — Gemini 2.0 Flash (1500 req/day free, generous token limits).
  if (isGeminiConfigured()) {
    const tgem = Date.now();
    try {
      const stream = await streamWithGemini(messages);
      log('provider.gemini.ok', {
        requestId,
        latencyMs: Date.now() - tgem,
        totalMs: Date.now() - startedAt,
      });
      return stream;
    } catch (error: any) {
      const msg = String(error?.message || error).slice(0, 200);
      log('provider.gemini.fail', { requestId, latencyMs: Date.now() - tgem, error: msg });
      failures.push(`gemini: ${msg}`);
    }
  } else {
    log('provider.gemini.skipped', { requestId, reason: 'not configured' });
  }

  // Step 3 — OpenRouter (free tier, no per-minute TPM cap like Groq).
  if (isOpenRouterConfigured()) {
    const tor = Date.now();
    try {
      const stream = await streamWithOpenRouter(messages);
      log('provider.openrouter.ok', {
        requestId,
        latencyMs: Date.now() - tor,
        totalMs: Date.now() - startedAt,
      });
      return stream;
    } catch (error: any) {
      const msg = String(error?.message || error).slice(0, 200);
      log('provider.openrouter.fail', { requestId, latencyMs: Date.now() - tor, error: msg });
      failures.push(`openrouter: ${msg}`);
    }
  } else {
    log('provider.openrouter.skipped', { requestId, reason: 'not configured' });
  }

  // Step 4 — OllaBridge (only when the admin has set OLLABRIDGE_URL).
  if (isOllaBridgeConfigured()) {
    const t0 = Date.now();
    try {
      const stream = await streamWithOllaBridge(messages, model);
      log('provider.ollabridge.ok', {
        requestId,
        latencyMs: Date.now() - t0,
        totalMs: Date.now() - startedAt,
      });
      return stream;
    } catch (error: any) {
      const msg = String(error?.message || error).slice(0, 200);
      log('provider.ollabridge.fail', {
        requestId,
        latencyMs: Date.now() - t0,
        error: msg,
      });
      failures.push(`ollabridge: ${msg}`);
    }
  } else {
    log('provider.ollabridge.skipped', { requestId, reason: 'not configured' });
  }

  // Step 4 — HuggingFace Inference (cascades internally, Mercury-STD-Mistral first).
  const t1 = Date.now();
  try {
    const stream = await streamWithHuggingFace(messages);
    log('provider.huggingface.ok', {
      requestId,
      latencyMs: Date.now() - t1,
      totalMs: Date.now() - startedAt,
    });
    return stream;
  } catch (error: any) {
    const msg = String(error?.message || error).slice(0, 200);
    log('provider.huggingface.fail', {
      requestId,
      latencyMs: Date.now() - t1,
      error: msg,
    });
    failures.push(`huggingface: ${msg}`);
  }

  // All providers failed. We do NOT pretend with a canned response.
  log('provider.all_failed', {
    requestId,
    totalMs: Date.now() - startedAt,
    failures,
  });
  throw new AllProvidersUnavailableError(
    'All LLM providers are currently unavailable. Please try again in a moment.',
  );
}

/**
 * Non-streaming chat completion with fallback chain.
 * Mirrors streamWithFallback — same decisions, same logs, same
 * AllProvidersUnavailableError on total failure.
 */
export async function chatWithFallback(
  messages: ChatMessage[],
  model: string = 'qwen2.5:1.5b'
): Promise<ProviderResponse> {
  const requestId = Math.random().toString(36).slice(2, 10);
  log('request.start.nonstream', { requestId, model });

  const failures: string[] = [];

  // Step 1 — Groq (primary).
  if (isGroqConfigured()) {
    const tg = Date.now();
    try {
      const resp = await chatWithGroq(messages, model);
      log('provider.groq.ok.nonstream', {
        requestId,
        latencyMs: Date.now() - tg,
        model: resp.model,
      });
      return resp;
    } catch (error: any) {
      const msg = String(error?.message || error).slice(0, 200);
      log('provider.groq.fail.nonstream', {
        requestId,
        latencyMs: Date.now() - tg,
        error: msg,
      });
      failures.push(`groq: ${msg}`);
    }
  } else {
    log('provider.groq.skipped.nonstream', { requestId });
  }

  // Step 2 — Gemini 2.0 Flash.
  if (isGeminiConfigured()) {
    try {
      const resp = await chatWithGemini(messages);
      log('provider.gemini.ok.nonstream', { requestId });
      return resp;
    } catch (error: any) {
      const msg = String(error?.message || error).slice(0, 200);
      log('provider.gemini.fail.nonstream', { requestId, error: msg });
      failures.push(`gemini: ${msg}`);
    }
  } else {
    log('provider.gemini.skipped.nonstream', { requestId });
  }

  // Step 3 — OpenRouter.
  if (isOpenRouterConfigured()) {
    try {
      const resp = await chatWithOpenRouter(messages);
      log('provider.openrouter.ok.nonstream', { requestId });
      return resp;
    } catch (error: any) {
      const msg = String(error?.message || error).slice(0, 200);
      log('provider.openrouter.fail.nonstream', { requestId, error: msg });
      failures.push(`openrouter: ${msg}`);
    }
  } else {
    log('provider.openrouter.skipped.nonstream', { requestId });
  }

  // Step 4 — OllaBridge.
  if (isOllaBridgeConfigured()) {
    try {
      const resp = await chatWithOllaBridge(messages, model);
      log('provider.ollabridge.ok.nonstream', { requestId });
      return resp;
    } catch (error: any) {
      const msg = String(error?.message || error).slice(0, 200);
      log('provider.ollabridge.fail.nonstream', { requestId, error: msg });
      failures.push(`ollabridge: ${msg}`);
    }
  } else {
    log('provider.ollabridge.skipped.nonstream', { requestId });
  }

  // Step 4 — HuggingFace Inference (Mercury-STD-Mistral first in chain).
  try {
    const resp = await chatWithHuggingFace(messages);
    log('provider.huggingface.ok.nonstream', { requestId });
    return resp;
  } catch (error: any) {
    const msg = String(error?.message || error).slice(0, 200);
    log('provider.huggingface.fail.nonstream', { requestId, error: msg });
    failures.push(`huggingface: ${msg}`);
  }

  log('provider.all_failed.nonstream', { requestId, failures });
  throw new AllProvidersUnavailableError(
    'All LLM providers are currently unavailable. Please try again in a moment.',
  );
}
