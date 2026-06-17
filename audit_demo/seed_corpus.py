"""
seed_corpus.py — Populate Mercury's live RAG corpus with 20 fictional patients.

Registers each user from seed_data.py, sends their messages sequentially
(with full conversation history so the LLM responds in context), and waits
for each LLM response before the next message — because addUserConversationChunk
now stores the actual response, not an empty string.

USAGE:
    1. Start Mercury:
         cd ai-medical-chatbot/9-HuggingFace-Global && npm run dev
    2. Run this script:
         python audit_demo/seed_corpus.py

REQUIRES: pip install requests
NOTE: Server must stay running between seeding and the attacker script —
      _userConversationChunks is in-memory and resets on restart.
"""

import json
import time
import sys
import os

import requests

sys.path.insert(0, os.path.dirname(__file__))
from seed_data import USERS

BASE_URL = 'http://localhost:7860'
DELAY_BETWEEN_MESSAGES = 1.5   # seconds — stays well under 60 msg/min rate limit
DELAY_BETWEEN_USERS    = 2.0   # seconds

SEP  = '─' * 65
SEP2 = '═' * 65


# ── API helpers ───────────────────────────────────────────────────────────────

def register_or_login(email: str, password: str, name: str) -> str:
    # Register endpoint allows only 5 registrations/min per IP.
    # Retry with backoff on 429 before falling through to login.
    for attempt in range(1, 4):
        r = requests.post(f'{BASE_URL}/api/auth/register', json={
            'email': email, 'password': password, 'displayName': name,
        }, timeout=15)

        if r.status_code == 201:
            return r.json()['token']

        if r.status_code == 409:
            # User already exists — fall through to login
            break

        if r.status_code == 429:
            wait = int(r.headers.get('Retry-After', 15))
            print(f'    ⏳ register rate-limited — waiting {wait}s (attempt {attempt}/3)...')
            time.sleep(wait + 1)
            continue

        # Any other error — log it and try login anyway
        print(f'    ⚠  register returned {r.status_code}: {r.text[:120]}')
        break

    r2 = requests.post(f'{BASE_URL}/api/auth/login', json={
        'email': email, 'password': password,
    }, timeout=15)
    if r2.status_code != 200:
        raise RuntimeError(f'Auth failed for {email}: {r2.text[:200]}')
    return r2.json()['token']


def inject_chunk(token: str, user_message: str) -> None:
    """
    Inject a message directly into the live RAG corpus via /api/audit/seed.
    No LLM call — zero API quota consumed.
    """
    r = requests.post(
        f'{BASE_URL}/api/audit/seed',
        headers={'Authorization': f'Bearer {token}'},
        json={'userMessage': user_message, 'assistantResponse': ''},
        timeout=15,
    )
    if r.status_code != 200:
        raise RuntimeError(f'Inject failed ({r.status_code}): {r.text[:300]}')


# ── Seeder ────────────────────────────────────────────────────────────────────

def seed_user(user: dict, index: int, total: int) -> dict:
    """Register user, send all their messages, return a summary dict."""
    name     = user['name']
    email    = user['email']
    password = user['password']
    topic    = user['topic']
    messages = user['messages']

    print(f'\n[{index}/{total}] {name}  ({topic})')
    print(f'        {email}')
    print(SEP)

    token = register_or_login(email, password, name)
    print(f'  ✓ authenticated')

    chunks_added = 0

    for i, user_msg in enumerate(messages, 1):
        print(f'  → inject {i}/{len(messages)}: {user_msg[:70].replace(chr(10), " ")}...')
        try:
            inject_chunk(token, user_msg)
            chunks_added += 1
            print(f'  ✓ injected')
        except RuntimeError as e:
            print(f'    ✗ error: {e}')
            break

        if i < len(messages):
            time.sleep(0.2)  # tiny delay — no rate limit to worry about

    print(f'  ✓ {chunks_added} chunk(s) added to live RAG corpus')
    return {
        'name':         name,
        'email':        email,
        'topic':        topic,
        'turns_seeded': chunks_added,
        'success':      chunks_added == len(messages),
    }


def main():
    print(f'\n{SEP2}')
    print('  MERCURY AUDIT — Live RAG Corpus Seeder')
    print(f'  Seeding {len(USERS)} users into _userConversationChunks')
    print(f'{SEP2}')

    # Quick connectivity check
    try:
        requests.get(f'{BASE_URL}/api/auth/me', timeout=5)
    except requests.exceptions.ConnectionError:
        print(f'\n  ERROR: Cannot reach Mercury at {BASE_URL}')
        print('  Start the server first:')
        print('    cd ai-medical-chatbot/9-HuggingFace-Global && npm run dev\n')
        sys.exit(1)

    results = []
    for i, user in enumerate(USERS, 1):
        result = seed_user(user, i, len(USERS))
        results.append(result)
        if i < len(USERS):
            time.sleep(DELAY_BETWEEN_USERS)

    # ── Summary ───────────────────────────────────────────────────────────────
    total_chunks = sum(r['turns_seeded'] for r in results)
    failed       = [r for r in results if not r['success']]

    print(f'\n{SEP2}')
    print('  SEEDING COMPLETE')
    print(f'{SEP2}')
    print(f'  Users seeded:        {len(results) - len(failed)} / {len(results)}')
    print(f'  Total RAG chunks:    {total_chunks}')
    print(f'  Failures:            {len(failed)}')
    if failed:
        for f in failed:
            print(f'    ✗ {f["name"]} ({f["email"]})')

    print()
    print('  Live RAG corpus is now populated.')
    print('  Run the attacker script next — do NOT restart the server.')
    print(f'  (restarting wipes _userConversationChunks)\n')

    # Save a manifest so the attacker script knows what was seeded
    manifest_path = os.path.join(os.path.dirname(__file__), 'seeded_manifest.json')
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total_users':  len(results),
            'total_chunks': total_chunks,
            'users':        results,
        }, f, indent=2, ensure_ascii=False)
    print(f'  Manifest saved to: {manifest_path}')


if __name__ == '__main__':
    main()
