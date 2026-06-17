import OpenAI from 'openai';
import type { ChatMessage, ProviderResponse } from './index';
import { loadConfig } from '@/lib/server-config';

const OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1';
const OPENROUTER_DEFAULT_MODEL = 'meta-llama/llama-3.1-8b-instruct';
const OPENROUTER_TIMEOUT_MS = 30_000;

function getKey(): string {
  try {
    const cfg = loadConfig();
    if (cfg.llm.openrouterApiKey) return cfg.llm.openrouterApiKey;
  } catch {
    // fall through to env
  }
  return process.env.OPENROUTER_API_KEY || '';
}

export function isOpenRouterConfigured(): boolean {
  return !!getKey();
}

function getClient(): OpenAI {
  return new OpenAI({
    baseURL: OPENROUTER_BASE_URL,
    apiKey: getKey(),
    timeout: OPENROUTER_TIMEOUT_MS,
    maxRetries: 0,
    defaultHeaders: {
      'HTTP-Referer': 'http://localhost:7860',
      'X-Title': 'Mercury Medical Chatbot',
    },
  });
}

export async function chatWithOpenRouter(
  messages: ChatMessage[],
): Promise<ProviderResponse> {
  const client = getClient();
  const response = await client.chat.completions.create({
    model: OPENROUTER_DEFAULT_MODEL,
    messages: messages.map((m) => ({ role: m.role, content: m.content })),
    max_tokens: 700,
    temperature: 0.4,
    top_p: 0.9,
  });
  return {
    content: response.choices[0]?.message?.content || '',
    provider: 'openrouter',
    model: response.model || OPENROUTER_DEFAULT_MODEL,
  };
}

export async function streamWithOpenRouter(
  messages: ChatMessage[],
): Promise<ReadableStream> {
  const client = getClient();
  const stream = await client.chat.completions.create({
    model: OPENROUTER_DEFAULT_MODEL,
    messages: messages.map((m) => ({ role: m.role, content: m.content })),
    max_tokens: 700,
    temperature: 0.4,
    top_p: 0.9,
    stream: true,
  });

  const encoder = new TextEncoder();
  return new ReadableStream({
    async start(controller) {
      try {
        for await (const chunk of stream) {
          const content = chunk.choices?.[0]?.delta?.content;
          if (content) {
            const data = JSON.stringify({
              choices: [{ delta: { content } }],
              provider: 'openrouter',
              model: chunk.model || OPENROUTER_DEFAULT_MODEL,
            });
            controller.enqueue(encoder.encode(`data: ${data}\n\n`));
          }
        }
        controller.enqueue(encoder.encode('data: [DONE]\n\n'));
        controller.close();
      } catch (error) {
        controller.error(error);
      }
    },
  });
}
