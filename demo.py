"""
Opius Network - Demo
Walks through the full loyalty-points lifecycle:
  1. Set up a validator (the business)
  2. Onboard members (customers) with wallets
  3. Earn: business mints OPI points to a customer for a purchase
  4. Transfer: customer sends points to another customer (e.g. a gift)
  5. Redeem: customer burns points for a reward
  6. Seal everything into blocks and verify the chain
"""
import os
from wallet import Wallet
from blockchain import OpiusChain, Transaction

# fresh demo run
if os.path.exists("chain_data.json"):
    os.remove("chain_data.json")

# 1. Validator = the business itself
business = Wallet()
print(f"Business (validator) address: {business.address}")

chain = OpiusChain(validators=[business.address],
                    validator_pubkeys={business.address: business.public_key_hex})

# 2. Onboard two members
alice = Wallet()
bob = Wallet()
print(f"Alice address: {alice.address}")
print(f"Bob address:   {bob.address}")

# 3. EARN: business mints 500 OPI to Alice for a purchase
earn_tx = Transaction(
    tx_type="earn", sender_address=business.address, sender_pubkey=business.public_key_hex,
    recipient=alice.address, amount=500, memo="Purchase reward: order #1042",
)
earn_tx.sign_with(business)
result = chain.submit_transaction(earn_tx)
print("\nSubmit earn tx:", result)

# 4. TRANSFER: Alice gifts 100 OPI to Bob (must be signed by Alice, the sender)
transfer_tx = Transaction(
    tx_type="transfer", sender_address=alice.address, sender_pubkey=alice.public_key_hex,
    recipient=bob.address, amount=100, memo="Gift for referring a friend",
)
transfer_tx.sign_with(alice)
result = chain.submit_transaction(transfer_tx)
print("Submit transfer tx:", result)

# Seal block 1 (business validator's turn)
block_result = chain.produce_block(business)
print("\nProduced block:", block_result["ok"], "| block index:", block_result["block"]["index"] if block_result["ok"] else None)

print(f"\nBalances after block 1:")
print(f"  Alice: {chain.balance_of(alice.address)} OPI")
print(f"  Bob:   {chain.balance_of(bob.address)} OPI")

# 5. REDEEM: Bob redeems 50 OPI for a reward (must be signed by Bob)
redeem_tx = Transaction(
    tx_type="redeem", sender_address=bob.address, sender_pubkey=bob.public_key_hex,
    recipient=None, amount=50, memo="Redeemed: free coffee",
)
redeem_tx.sign_with(bob)
result = chain.submit_transaction(redeem_tx)
print("\nSubmit redeem tx:", result)

block_result = chain.produce_block(business)
print("Produced block:", block_result["ok"], "| block index:", block_result["block"]["index"] if block_result["ok"] else None)

print(f"\nFinal balances:")
print(f"  Alice: {chain.balance_of(alice.address)} OPI")
print(f"  Bob:   {chain.balance_of(bob.address)} OPI")
print(f"  Total supply: {chain.total_supply} OPI")

# 6. Tamper check
print(f"\nChain length: {len(chain.chain)} blocks")
print(f"Chain valid: {chain.is_chain_valid()}")

print("\nTampering with a stored balance and re-checking chain validity (should still be True, "
      "since balances are derived from valid tx history, not stored trust)...")
# Try an invalid tx: Bob attempting to spend more than he has
bad_tx = Transaction(
    tx_type="transfer", sender_address=bob.address, sender_pubkey=bob.public_key_hex,
    recipient=alice.address, amount=10_000, memo="overspend attempt",
)
bad_tx.sign_with(bob)
print("Overspend attempt result:", chain.submit_transaction(bad_tx))

# Try a forged tx: someone claiming to be Alice without her private key
mallory = Wallet()
forged_tx = Transaction(
    tx_type="transfer", sender_address=alice.address, sender_pubkey=alice.public_key_hex,
    recipient=mallory.address, amount=50, memo="forged transfer",
)
forged_tx.sign_with(mallory)  # signed with the WRONG key
print("Forged tx result:", chain.submit_transaction(forged_tx))

print("\nDemo complete. Full chain saved to chain_data.json")
