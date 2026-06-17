import OpenAI from 'openai';
import type { ChatMessage, ProviderResponse } from './index';

const GEMINI_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/openai/';
const GEMINI_MODEL = 'gemini-2.0-flash-lite';
const GEMINI_TIMEOUT_MS = 30_000;

function getKey(): string {
  return process.env.GEMINI_API_KEY || '';
}

export function isGeminiConfigured(): boolean {
  return !!getKey();
}

function getClient(): OpenAI {
  return new OpenAI({
    baseURL: GEMINI_BASE_URL,
    apiKey: getKey(),
    timeout: GEMINI_TIMEOUT_MS,
    maxRetries: 0,
  });
}

export async function chatWithGemini(
  messages: ChatMessage[],
): Promise<ProviderResponse> {
  const client = getClient();
  const response = await client.chat.completions.create({
    model: GEMINI_MODEL,
    messages: messages.map((m) => ({ role: m.role, content: m.content })),
    max_tokens: 700,
    temperature: 0.4,
  });
  return {
    content: response.choices[0]?.message?.content || '',
    provider: 'gemini',
    model: response.model || GEMINI_MODEL,
  };
}

export async function streamWithGemini(
  messages: ChatMessage[],
): Promise<ReadableStream> {
  const client = getClient();
  const stream = await client.chat.completions.create({
    model: GEMINI_MODEL,
    messages: messages.map((m) => ({ role: m.role, content: m.content })),
    max_tokens: 700,
    temperature: 0.4,
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
              provider: 'gemini',
              model: chunk.model || GEMINI_MODEL,
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
