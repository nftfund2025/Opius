# Opius Network

A private, Proof-of-Authority blockchain built from scratch for a business loyalty points program.

## What's here

| File | Purpose |
|---|---|
| `wallet.py` | Keypair generation (SECP256K1, same curve as Bitcoin/Ethereum), address derivation, signing & verification |
| `blockchain.py` | Core chain: transactions, blocks, PoA consensus, ledger state, persistence |
| `node.py` | Flask API server — the thing your POS/app backend actually talks to |
| `client_example.py` | Shows how a *member* signs their own transactions locally, without sending their private key anywhere |
| `demo.py` | Standalone script proving out the whole lifecycle + attack resistance |

## How it works

- **Consensus:** Proof of Authority. Whitelisted validator address(es) — your business — take turns
  sealing blocks. No mining, no energy cost, ~instant finality.
- **Points (OPI):** minted on `earn`, burned on `redeem`, moved peer-to-peer on `transfer`.
- **Security model:** every transaction is signed with ECDSA by its sender. The node verifies the
  signature against the claimed address before accepting anything — nobody can spend, mint, or forge
  a transaction on someone else's behalf. This was tested against both an overspend attempt and a
  forged-signature attempt in `demo.py`, both correctly rejected.
- **Persistence:** the full chain + balances save to `chain_data.json` after every block.

## Try it

**Standalone demo (no server needed):**
```bash
pip install cryptography
python3 demo.py
```

**Run as a live API:**
```bash
pip install cryptography flask requests
python3 node.py
# server starts on http://localhost:5000
# creates business_wallet.json on first run -- this is your business's signing key, keep it secret
```

**Endpoints:**
- `POST /wallet/new` — create a member wallet (demo only; in production generate keys client-side)
- `POST /earn` — business mints points to a customer: `{"recipient": "...", "amount": 300, "memo": "..."}`
- `POST /transfer` — member-to-member transfer, must be pre-signed (see `client_example.py`)
- `POST /redeem` — member burns points for a reward, must be pre-signed
- `GET /balance/<address>` — check a balance
- `GET /chain` — full chain + validity check
- `GET /stats` — quick summary

**See the client-signing flow (the realistic way an app would use this):**
```bash
python3 node.py &
python3 client_example.py
```

## Scaling this to 1000 members

This single-validator setup already comfortably handles 1000 members — it's a few thousand
transactions at most, trivial for this design. To harden it for real production use:

1. **Multiple validators** — add 3-5 validator addresses instead of 1, so no single machine is a
   point of failure. `blockchain.py`'s round-robin logic already supports this; you'd add real
   networking (gossip/sync between nodes) since right now it's single-process.
2. **Client-side key generation** — right now `/wallet/new` generates keys server-side for demo
   convenience. In production, generate keys in the customer's app/browser (e.g. via WebCrypto or
   a mobile SDK) so the business never sees private keys at all.
3. **Rate limiting / auth on `/earn`** — right now anyone who can reach the API can trigger a mint.
   Lock this down to your authenticated POS/backend only.
4. **HTTPS + a real WSGI server** (gunicorn/uwsgi) instead of Flask's dev server.
5. **Database instead of JSON file** — swap `chain_data.json` for Postgres/SQLite once you're past
   prototyping, for concurrent write safety.

## Design notes / what makes it "from scratch"

Unlike using an existing chain, every piece here is custom: the transaction format, block structure,
consensus rule (validator rotation), and ledger logic are all Opius Network's own code — not a fork
of Bitcoin, Ethereum, or Solana. The only external building blocks are `cryptography` (for the
actual elliptic-curve math, which you should never hand-roll) and `Flask` (for the HTTP layer).
