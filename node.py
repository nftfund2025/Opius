"""
Opius Network - API Node
Run this to expose the chain over HTTP so a POS system, app backend, or
merchant dashboard can talk to Opius Network without touching raw crypto.

Usage:
    python3 node.py
    (starts on http://localhost:5000)

On first run, it creates a business validator wallet and saves it to
business_wallet.json — KEEP THIS FILE SECRET, it's the only account allowed
to mint (earn) points.
"""
import json
import os
from flask import Flask, request, jsonify, send_from_directory
from wallet import Wallet
from blockchain import OpiusChain, Transaction

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Secret"
    return response


@app.route("/<path:path>", methods=["OPTIONS"])
def cors_preflight(path):
    return "", 204

BUSINESS_WALLET_FILE = os.path.join(os.environ.get("DATA_DIR", os.path.dirname(__file__)), "business_wallet.json")

# --- bootstrap the business (validator) wallet ---
if os.path.exists(BUSINESS_WALLET_FILE):
    with open(BUSINESS_WALLET_FILE) as f:
        wdata = json.load(f)
    business = Wallet.from_private_key_hex(wdata["private_key"])
else:
    business = Wallet()
    with open(BUSINESS_WALLET_FILE, "w") as f:
        json.dump(business.to_dict(), f, indent=2)
    print(f"Created new business validator wallet -> {BUSINESS_WALLET_FILE}")

chain = OpiusChain(validators=[business.address],
                    validator_pubkeys={business.address: business.public_key_hex})

print(f"Opius Network node starting. Business/validator address: {business.address}")


def auto_seal():
    """For this single-validator demo node, immediately seal every accepted tx into a block
    so balances update in real time. A multi-validator deployment would instead run this
    on a timer/round-robin schedule."""
    if chain.mempool:
        chain.produce_block(business)


@app.route("/", methods=["GET"])
def serve_frontend():
    """Serves the member passbook web app at the node's root URL, so members can just
    visit a link instead of downloading a file."""
    return send_from_directory(os.path.dirname(__file__), "index.html")


@app.route("/explorer", methods=["GET"])
def serve_explorer():
    """Serves the public block explorer."""
    return send_from_directory(os.path.dirname(__file__), "explorer.html")
def new_wallet():
    """Create a new member wallet. In production the private key should be generated
    client-side (never sent to the server) -- this endpoint is for demo convenience."""
    w = Wallet()
    return jsonify(w.to_dict())


@app.route("/balance/<address>", methods=["GET"])
def get_balance(address):
    return jsonify({"address": address, "balance": chain.balance_of(address)})


@app.route("/earn", methods=["POST"])
def earn():
    """Business mints loyalty points to a customer. Signed by the business wallet server-side
    since only the business is allowed to mint. Requires a secret admin key so this can't be
    triggered by anyone who has the frontend's source code -- only someone who also knows the key."""
    admin_secret = os.environ.get("ADMIN_SECRET")
    provided = request.headers.get("X-Admin-Secret", "")
    if admin_secret and provided != admin_secret:
        return jsonify({"ok": False, "error": "unauthorized: missing or incorrect admin key"}), 401

    data = request.json
    recipient = data["recipient"]
    amount = int(data["amount"])
    memo = data.get("memo", "")

    tx = Transaction(tx_type="earn", sender_address=business.address,
                      sender_pubkey=business.public_key_hex, recipient=recipient,
                      amount=amount, memo=memo)
    tx.sign_with(business)
    result = chain.submit_transaction(tx)
    if result["ok"]:
        auto_seal()
        result["balance"] = chain.balance_of(recipient)
    return jsonify(result)


@app.route("/transfer", methods=["POST"])
def transfer():
    """Member-to-member transfer. Must be pre-signed client-side and submitted here --
    the server never sees the sender's private key."""
    data = request.json
    required = {"sender_address", "sender_pubkey", "recipient", "amount", "signature", "timestamp"}
    if not required.issubset(data):
        return jsonify({"ok": False, "error": f"missing fields, need: {required}"}), 400

    tx = Transaction(tx_type="transfer", sender_address=data["sender_address"],
                      sender_pubkey=data["sender_pubkey"], recipient=data["recipient"],
                      amount=int(data["amount"]), memo=data.get("memo", ""),
                      timestamp=data["timestamp"], signature=data["signature"])
    result = chain.submit_transaction(tx)
    if result["ok"]:
        auto_seal()
    return jsonify(result)


@app.route("/redeem", methods=["POST"])
def redeem():
    """Member burns points for a reward. Must be pre-signed client-side."""
    data = request.json
    required = {"sender_address", "sender_pubkey", "amount", "signature", "timestamp"}
    if not required.issubset(data):
        return jsonify({"ok": False, "error": f"missing fields, need: {required}"}), 400

    tx = Transaction(tx_type="redeem", sender_address=data["sender_address"],
                      sender_pubkey=data["sender_pubkey"], recipient=None,
                      amount=int(data["amount"]), memo=data.get("memo", ""),
                      timestamp=data["timestamp"], signature=data["signature"])
    result = chain.submit_transaction(tx)
    if result["ok"]:
        auto_seal()
    return jsonify(result)


@app.route("/chain", methods=["GET"])
def get_chain():
    return jsonify({
        "length": len(chain.chain),
        "valid": chain.is_chain_valid(),
        "total_supply": chain.total_supply,
        "blocks": [b.to_dict() for b in chain.chain],
    })


@app.route("/stats", methods=["GET"])
def stats():
    return jsonify({
        "business_address": business.address,
        "total_supply": chain.total_supply,
        "blocks": len(chain.chain),
        "members_with_balance": len([a for a, b in chain.balances.items() if b > 0]),
        "chain_valid": chain.is_chain_valid(),
    })


if __name__ == "__main__":
    import os as _os
    port = int(_os.environ.get("PORT", 5000))
    debug = _os.environ.get("OPIUS_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
