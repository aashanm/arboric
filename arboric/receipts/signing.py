"""ECDSA P-256-SHA256 cryptographic signing for carbon receipts."""

import hashlib
from datetime import datetime
from pathlib import Path

from arboric.receipts.exceptions import EnterpriseFeatureNotAvailableError, SigningError
from arboric.receipts.models import CarbonReceipt, CryptoSignature

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import (
        load_pem_private_key,
        load_pem_public_key,
    )
except ImportError as e:
    raise EnterpriseFeatureNotAvailableError(
        "cryptography not found. Install: pip install arboric[enterprise]"
    ) from e


def generate_keypair() -> tuple[bytes, bytes]:
    """
    Generate a new ECDSA P-256 keypair.

    Returns:
        Tuple of (private_pem, public_pem) as bytes.
    """
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    return private_pem, public_pem


def load_or_create_keypair() -> tuple:
    """
    Load keypair from ~/.arboric/keys/ or generate and persist on first use.

    Returns:
        Tuple of (private_key, public_key) cryptography objects.
    """
    key_dir = Path.home() / ".arboric" / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)

    private_path = key_dir / "private_key.pem"
    public_path = key_dir / "public_key.pem"

    if private_path.exists() and public_path.exists():
        with open(private_path, "rb") as f:
            private_pem = f.read()
        with open(public_path, "rb") as f:
            public_pem = f.read()
    else:
        private_pem, public_pem = generate_keypair()
        private_path.write_bytes(private_pem)
        private_path.chmod(0o600)  # chmod 600 for security
        public_path.write_bytes(public_pem)

    private_key = load_pem_private_key(private_pem, password=None, backend=default_backend())
    public_key = load_pem_public_key(public_pem, backend=default_backend())

    return private_key, public_key


def fingerprint(public_key) -> str:
    """
    Compute SHA256 fingerprint of DER-encoded public key.

    Args:
        public_key: A cryptography PublicKey object.

    Returns:
        64-character hex string.
    """
    der_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der_bytes).hexdigest()


def sign_receipt(receipt: CarbonReceipt) -> CryptoSignature:
    """
    Sign a carbon receipt with ECDSA-P256-SHA256.

    Args:
        receipt: The CarbonReceipt to sign (signature field must be None).

    Returns:
        CryptoSignature with algorithm, fingerprint, signature_hex, data_hash, signed_at.

    Raises:
        SigningError: If signing fails.
    """
    try:
        canonical = receipt.canonical_json()
        data_hash = hashlib.sha256(canonical.encode()).hexdigest()

        private_key, public_key = load_or_create_keypair()
        sig_bytes = private_key.sign(
            canonical.encode(),
            ec.ECDSA(hashes.SHA256()),
        )

        return CryptoSignature(
            algorithm="ECDSA-P256-SHA256",
            public_key_fingerprint=fingerprint(public_key),
            signature_hex=sig_bytes.hex(),
            data_hash=data_hash,
            signed_at=datetime.utcnow(),
        )
    except Exception as e:
        raise SigningError(f"Failed to sign receipt: {e}") from e


def verify_receipt(receipt: CarbonReceipt, public_key_pem: bytes | None = None) -> bool:
    """
    Verify a signed carbon receipt.

    Args:
        receipt: The CarbonReceipt to verify.
        public_key_pem: Optional public key PEM bytes. If None, loads from ~/.arboric/keys/.

    Returns:
        True if signature is valid, False otherwise (including if signature is None).
    """
    if receipt.signature is None:
        return False

    try:
        if public_key_pem is None:
            _, public_key = load_or_create_keypair()
        else:
            public_key = load_pem_public_key(public_key_pem, backend=default_backend())

        canonical = receipt.canonical_json()
        sig_bytes = bytes.fromhex(receipt.signature.signature_hex)

        public_key.verify(
            sig_bytes,
            canonical.encode(),
            ec.ECDSA(hashes.SHA256()),
        )
        return True
    except Exception:
        return False
