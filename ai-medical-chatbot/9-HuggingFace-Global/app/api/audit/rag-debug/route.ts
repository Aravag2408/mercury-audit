import { NextRequest } from 'next/server';
import { authenticateRequest } from '@/lib/auth-middleware';
import { searchMedicalKB } from '@/lib/rag/medical-kb';

/**
 * POST /api/audit/rag-debug
 *
 * Shows exactly what RAG chunks get injected into the LLM context for a given
 * query — including live conversation chunks from other users.
 *
 * This endpoint is the privacy audit "smoking gun": it proves that User B's
 * query retrieves User A's private conversation chunks with no access control.
 */
export async function POST(request: NextRequest) {
  const user = authenticateRequest(request);
  if (!user) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const { query } = await request.json();
  if (!query || typeof query !== 'string') {
    return new Response(JSON.stringify({ error: 'query required' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const results = searchMedicalKB(query, 5);

  return new Response(
    JSON.stringify({
      query,
      requesting_user: user.id,
      retrieved_chunks: results.map((r) => ({
        source: r.topic,
        is_live_conversation: r.topic === 'user conversation',
        content: r.context,
      })),
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  );
}
