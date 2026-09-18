"""
Opius Network - Client Example
Shows how a MEMBER (not the business) signs their own transfer/redeem
transactions locally -- their private key never has to leave their device
and never gets sent to the API node.

Run node.py first, then run this script.
"""
import time
import requests
from wallet import Wallet

NODE_URL = "http://localhost:5000"


def sign_payload(wallet, tx_type, recipient, amount, memo=""):
    """Build and sign the exact payload the node expects, matching Transaction.signing_payload()."""
    timestamp = time.time()
    payload = {
        "tx_type": tx_type,
        "sender_address": wallet.address,
        "sender_pubkey": wallet.public_key_hex,
        "recipient": recipient,
        "amount": amount,
        "memo": memo,
        "timestamp": timestamp,
    }
    signature = wallet.sign(payload)
    payload["signature"] = signature
    return payload


if __name__ == "__main__":
    # 1. Create two local member wallets (in a real app: generated on the user's device/app)
    alice = Wallet()
    bob = Wallet()
    print(f"Alice: {alice.address}")
    print(f"Bob:   {bob.address}")

    # 2. Ask the business (server-side) to mint points to Alice for a purchase
    r = requests.post(f"{NODE_URL}/earn", json={
        "recipient": alice.address, "amount": 400, "memo": "purchase reward",
    })
    print("Earn:", r.json())

    # 3. Alice transfers 150 points to Bob -- SIGNED LOCALLY with her own private key
    transfer_payload = sign_payload(alice, "transfer", bob.address, 150, memo="gift")
    r = requests.post(f"{NODE_URL}/transfer", json=transfer_payload)
    print("Transfer:", r.json())

    # 4. Bob redeems 50 points -- also signed locally
    redeem_payload = sign_payload(bob, "redeem", None, 50, memo="free coffee")
    r = requests.post(f"{NODE_URL}/redeem", json=redeem_payload)
    print("Redeem:", r.json())

    # 5. Check final balances
    print("Alice balance:", requests.get(f"{NODE_URL}/balance/{alice.address}").json())
    print("Bob balance:  ", requests.get(f"{NODE_URL}/balance/{bob.address}").json())
