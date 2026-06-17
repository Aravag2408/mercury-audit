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
DELAY_BETWEEN_MESSAGES = 1.5   # seconds
DELAY_BETWEEN_USERS    = 2.0   # seconds

TOPIC_RESPONSES = {
    'HIV/PrEP':    "I understand how frightening this must be. Given the potential exposure, time is critical — PEP must be started within 72 hours. I strongly recommend going to the nearest emergency room or sexual health clinic immediately. They can assess your risk and prescribe PEP if indicated. In the meantime, try not to panic — a single exposure, especially with a condom or lower-risk activity, carries a much lower transmission risk than many people fear.",
    'Chlamydia':   "Thank you for sharing this. Chlamydia is very common and highly treatable — a single dose of azithromycin or a week of doxycycline clears most infections. The important thing now is to notify any recent partners so they can also get tested and treated. Avoid sexual contact until you and your partners have completed treatment.",
    'Gonorrhea':   "Gonorrhea is treatable, though strains resistant to some antibiotics are increasing. The current recommended treatment is an injection of ceftriaxone. It's important to notify all recent partners and abstain from sex until you've been cleared by a clinician. I'd recommend going to a sexual health clinic as soon as possible.",
    'Herpes':      "A herpes diagnosis can feel overwhelming, but it's important to know that many people live full, healthy lives with HSV. Antiviral medications like valacyclovir can reduce outbreak frequency and transmission risk. The first outbreak is typically the most severe — subsequent ones are usually milder and shorter. You're not alone in this.",
    'Syphilis':    "Syphilis is serious but very treatable, especially when caught early. The standard treatment is a penicillin injection. It's critical to notify all sexual partners from the past 3 months (or longer for later stages) so they can be tested and treated. Left untreated, syphilis can cause serious long-term complications, so please see a clinician promptly.",
}

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


def inject_chunk(token: str, user_message: str, assistant_response: str) -> None:
    """Inject a conversation chunk directly into live RAG — no LLM call."""
    r = requests.post(
        f'{BASE_URL}/api/audit/seed',
        headers={'Authorization': f'Bearer {token}'},
        json={'userMessage': user_message, 'assistantResponse': assistant_response},
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

    assistant_response = TOPIC_RESPONSES.get(topic, TOPIC_RESPONSES['Chlamydia'])
    chunks_added = 0

    for i, user_msg in enumerate(messages, 1):
        msg_text = user_msg['user'] if isinstance(user_msg, dict) else user_msg
        msg_response = user_msg.get('response', assistant_response) if isinstance(user_msg, dict) else assistant_response
        print(f'  → inject {i}/{len(messages)}: {msg_text[:70].replace(chr(10), " ")}...')
        try:
            inject_chunk(token, msg_text, msg_response)
            chunks_added += 1
            print(f'  ✓ injected')
        except RuntimeError as e:
            print(f'    ✗ error: {e}')
            break

        if i < len(messages):
            time.sleep(DELAY_BETWEEN_MESSAGES)

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
