"""
Opius Network - Wallet
Handles keypair generation, address derivation, signing and verification.
Uses SECP256K1 (same curve as Bitcoin/Ethereum) via the `cryptography` library.
"""
import hashlib
import json
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.exceptions import InvalidSignature


def _address_from_public_key(public_key: ec.EllipticCurvePublicKey) -> str:
    """Derive a short human-friendly address from a public key (like a wallet address)."""
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    digest = hashlib.sha256(raw).hexdigest()
    return "opi1" + digest[-40:]  # 40 hex chars, prefixed like a bech32-style address


class Wallet:
    def __init__(self, private_key: ec.EllipticCurvePrivateKey = None):
        self.private_key = private_key or ec.generate_private_key(ec.SECP256K1())
        self.public_key = self.private_key.public_key()
        self.address = _address_from_public_key(self.public_key)

    @property
    def public_key_hex(self) -> str:
        raw = self.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        return raw.hex()

    @property
    def private_key_hex(self) -> str:
        raw = self.private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return raw.hex()

    @classmethod
    def from_private_key_hex(cls, hex_str: str) -> "Wallet":
        raw = bytes.fromhex(hex_str)
        pk = serialization.load_der_private_key(raw, password=None)
        return cls(private_key=pk)

    def sign(self, message: dict) -> str:
        """Sign a JSON-serializable message dict, return hex signature."""
        payload = json.dumps(message, sort_keys=True).encode()
        signature = self.private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        return signature.hex()

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "public_key": self.public_key_hex,
            "private_key": self.private_key_hex,
        }


def verify_signature(public_key_hex: str, message: dict, signature_hex: str) -> bool:
    """Verify a signature against a public key (hex) and message dict."""
    try:
        raw_pub = bytes.fromhex(public_key_hex)
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), raw_pub)
        payload = json.dumps(message, sort_keys=True).encode()
        public_key.verify(bytes.fromhex(signature_hex), payload, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, Exception):
        return False


def address_from_public_key_hex(public_key_hex: str) -> str:
    raw_pub = bytes.fromhex(public_key_hex)
    public_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), raw_pub)
    return _address_from_public_key(public_key)


if __name__ == "__main__":
    w = Wallet()
    print("New wallet created:")
    print(json.dumps(w.to_dict(), indent=2))
