import { NextRequest } from 'next/server';
import { authenticateRequest } from '@/lib/auth-middleware';
import { addUserConversationChunk } from '@/lib/rag/medical-kb';
import { z } from 'zod';

const Schema = z.object({
  userMessage:       z.string().min(1),
  assistantResponse: z.string().default(''),
});

/**
 * POST /api/audit/seed
 *
 * Injects a conversation chunk directly into _userConversationChunks for the
 * authenticated user — without calling any LLM. Used by the audit seeder to
 * populate the live RAG corpus without consuming API quota.
 *
 * Requires a valid Bearer token (any registered user). Each injected chunk is
 * scoped to the token holder's user ID, exactly as a real chat turn would be.
 */
export async function POST(request: NextRequest) {
  const user = authenticateRequest(request);
  if (!user) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: 'Invalid JSON' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const parsed = Schema.safeParse(body);
  if (!parsed.success) {
    return new Response(JSON.stringify({ error: 'Bad request', details: parsed.error.errors }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const { userMessage, assistantResponse } = parsed.data;
  await addUserConversationChunk(user.id, userMessage, assistantResponse);

  return new Response(JSON.stringify({ ok: true, userId: user.id }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}
