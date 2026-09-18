"""
Opius Network - Core Chain
A small Proof-of-Authority blockchain purpose-built for a loyalty points system
(mint on earn, burn on redeem, transfer between members).

Design:
- Consensus: Proof of Authority. A fixed, whitelisted set of validator addresses
  take turns signing blocks in round-robin order. No mining, no staking.
- Ledger: account balances keyed by wallet address, held in-memory + persisted to disk.
- Transactions: earn (mint), redeem (burn), transfer (p2p), each signed by the sender's
  private key and verified against their public key before being applied.
"""
import hashlib
import json
import time
import os
from wallet import verify_signature, address_from_public_key_hex

GENESIS_PREV_HASH = "0" * 64
CHAIN_FILE = os.path.join(os.path.dirname(__file__), "chain_data.json")

TX_TYPES = {"earn", "redeem", "transfer", "genesis"}


class Transaction:
    def __init__(self, tx_type, sender_address, sender_pubkey, recipient, amount,
                 memo="", timestamp=None, signature=None):
        if tx_type not in TX_TYPES:
            raise ValueError(f"Invalid tx type: {tx_type}")
        self.tx_type = tx_type
        self.sender_address = sender_address      # who authorizes this (issuer for earn/redeem, payer for transfer)
        self.sender_pubkey = sender_pubkey         # hex public key, used to verify signature
        self.recipient = recipient                 # address receiving points (or None for redeem)
        self.amount = amount
        self.memo = memo
        self.timestamp = timestamp or time.time()
        self.signature = signature

    def signing_payload(self) -> dict:
        return {
            "tx_type": self.tx_type,
            "sender_address": self.sender_address,
            "sender_pubkey": self.sender_pubkey,
            "recipient": self.recipient,
            "amount": self.amount,
            "memo": self.memo,
            "timestamp": self.timestamp,
        }

    def sign_with(self, wallet):
        self.signature = wallet.sign(self.signing_payload())

    def is_valid(self) -> bool:
        if self.tx_type == "genesis":
            return True
        if self.amount is None or self.amount <= 0:
            return False
        if not self.signature or not self.sender_pubkey:
            return False
        # sender_address must match the public key that signed it
        if address_from_public_key_hex(self.sender_pubkey) != self.sender_address:
            return False
        return verify_signature(self.sender_pubkey, self.signing_payload(), self.signature)

    def hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()

    def to_dict(self) -> dict:
        d = self.signing_payload()
        d["signature"] = self.signature
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(
            tx_type=d["tx_type"], sender_address=d["sender_address"],
            sender_pubkey=d["sender_pubkey"], recipient=d["recipient"],
            amount=d["amount"], memo=d.get("memo", ""),
            timestamp=d["timestamp"], signature=d.get("signature"),
        )


class Block:
    def __init__(self, index, prev_hash, transactions, validator, timestamp=None, validator_signature=None):
        self.index = index
        self.prev_hash = prev_hash
        self.transactions = transactions  # list[Transaction]
        self.validator = validator        # address of validator who produced this block
        self.timestamp = timestamp or time.time()
        self.validator_signature = validator_signature

    def header(self) -> dict:
        return {
            "index": self.index,
            "prev_hash": self.prev_hash,
            "tx_hashes": [tx.hash() for tx in self.transactions],
            "validator": self.validator,
            "timestamp": self.timestamp,
        }

    def hash(self) -> str:
        payload = json.dumps(self.header(), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()

    def sign_with(self, validator_wallet):
        self.validator_signature = validator_wallet.sign(self.header())

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "prev_hash": self.prev_hash,
            "hash": self.hash(),
            "validator": self.validator,
            "timestamp": self.timestamp,
            "validator_signature": self.validator_signature,
            "transactions": [tx.to_dict() for tx in self.transactions],
        }

    @classmethod
    def from_dict(cls, d):
        txs = [Transaction.from_dict(t) for t in d["transactions"]]
        b = cls(d["index"], d["prev_hash"], txs, d["validator"], d["timestamp"], d["validator_signature"])
        return b


class OpiusChain:
    """The Opius Network ledger: PoA blockchain + account balances."""

    def __init__(self, validators, validator_pubkeys):
        """
        validators: list of validator addresses, in round-robin signing order
        validator_pubkeys: dict {address: public_key_hex} for verifying block signatures
        """
        self.validators = validators
        self.validator_pubkeys = validator_pubkeys
        self.chain = []            # list[Block]
        self.balances = {}         # address -> int (OPI points)
        self.mempool = []          # pending Transaction objects
        self.total_supply = 0

        if os.path.exists(CHAIN_FILE):
            self._load()
        else:
            self._create_genesis_block()
            self._save()

    # ---------- genesis ----------
    def _create_genesis_block(self):
        genesis_tx = Transaction(
            tx_type="genesis", sender_address="opius-network", sender_pubkey="",
            recipient=None, amount=0, memo="Opius Network genesis block", timestamp=time.time(),
        )
        block = Block(index=0, prev_hash=GENESIS_PREV_HASH, transactions=[genesis_tx],
                       validator=self.validators[0])
        self.chain.append(block)

    # ---------- validator rotation ----------
    def next_validator(self) -> str:
        return self.validators[len(self.chain) % len(self.validators)]

    # ---------- transactions ----------
    def _projected_balance(self, address: str) -> int:
        """Confirmed balance plus the net effect of this address's own txs still sitting in mempool.
        Used so multiple pending transactions from the same sender can't double-spend before a block seals."""
        bal = self.balances.get(address, 0)
        for tx in self.mempool:
            if tx.sender_address == address and tx.tx_type in ("redeem", "transfer"):
                bal -= tx.amount
            if tx.recipient == address and tx.tx_type in ("earn", "transfer"):
                bal += tx.amount
        return bal

    def submit_transaction(self, tx: Transaction) -> dict:
        if not tx.is_valid():
            return {"ok": False, "error": "invalid signature or transaction"}

        if tx.tx_type == "earn":
            # Only whitelisted validators (the business) can mint points
            if tx.sender_address not in self.validators:
                return {"ok": False, "error": "only a validator (business account) can mint (earn) points"}
        elif tx.tx_type in ("redeem", "transfer"):
            if self._projected_balance(tx.sender_address) < tx.amount:
                return {"ok": False, "error": f"insufficient balance to {tx.tx_type}"}

        self.mempool.append(tx)
        return {"ok": True, "tx_hash": tx.hash()}

    def _apply_transaction(self, tx: Transaction):
        if tx.tx_type == "earn":
            self.balances[tx.recipient] = self.balances.get(tx.recipient, 0) + tx.amount
            self.total_supply += tx.amount
        elif tx.tx_type == "redeem":
            self.balances[tx.sender_address] -= tx.amount
            self.total_supply -= tx.amount
        elif tx.tx_type == "transfer":
            self.balances[tx.sender_address] -= tx.amount
            self.balances[tx.recipient] = self.balances.get(tx.recipient, 0) + tx.amount

    # ---------- block production ----------
    def produce_block(self, validator_wallet) -> dict:
        """Called by whichever validator's turn it is to seal the current mempool into a block.
        Transactions are applied strictly in submission order, rechecking balances as state
        updates block-by-block (this is what lets an earn+transfer land in the same block)."""
        expected = self.next_validator()
        if validator_wallet.address != expected:
            return {"ok": False, "error": f"not this validator's turn, expected {expected}"}

        included, skipped = [], []
        for tx in self.mempool:
            if not tx.is_valid():
                skipped.append(tx)
                continue
            if tx.tx_type == "earn" and tx.sender_address not in self.validators:
                skipped.append(tx)
                continue
            if tx.tx_type in ("redeem", "transfer") and self.balances.get(tx.sender_address, 0) < tx.amount:
                skipped.append(tx)
                continue
            self._apply_transaction(tx)
            included.append(tx)

        if not included:
            return {"ok": False, "error": "no valid pending transactions"}

        prev_hash = self.chain[-1].hash()
        block = Block(index=len(self.chain), prev_hash=prev_hash,
                       transactions=included, validator=validator_wallet.address)
        block.sign_with(validator_wallet)

        self.chain.append(block)
        self.mempool = skipped  # anything that failed stays pending; nothing is silently dropped
        self._save()
        return {"ok": True, "block": block.to_dict(), "included": len(included), "skipped": len(skipped)}

    # ---------- validation ----------
    def is_chain_valid(self) -> bool:
        for i in range(1, len(self.chain)):
            block = self.chain[i]
            prev = self.chain[i - 1]
            if block.prev_hash != prev.hash():
                return False
            pubkey = self.validator_pubkeys.get(block.validator)
            if not pubkey or not verify_signature(pubkey, block.header(), block.validator_signature):
                return False
            for tx in block.transactions:
                if not tx.is_valid():
                    return False
        return True

    # ---------- persistence ----------
    def _save(self):
        data = {
            "validators": self.validators,
            "validator_pubkeys": self.validator_pubkeys,
            "chain": [b.to_dict() for b in self.chain],
            "balances": self.balances,
            "total_supply": self.total_supply,
        }
        with open(CHAIN_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def _load(self):
        with open(CHAIN_FILE) as f:
            data = json.load(f)
        self.validators = data["validators"]
        self.validator_pubkeys = data["validator_pubkeys"]
        self.chain = [Block.from_dict(b) for b in data["chain"]]
        self.balances = data["balances"]
        self.total_supply = data["total_supply"]

    def balance_of(self, address: str) -> int:
        return self.balances.get(address, 0)
