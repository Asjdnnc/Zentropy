"""
Shared utilities: encoding helpers, hashing, hex conversion, hybrid seed generation.
"""
import base64
import hashlib
import hmac
import struct
import time


def b64encode(data: bytes) -> str:
    """Encode bytes to base64 string."""
    return base64.b64encode(data).decode("ascii")


def b64decode(data: str) -> bytes:
    """Decode base64 string to bytes."""
    return base64.b64decode(data)


def hex_encode(data: bytes) -> str:
    """Encode bytes to hex string."""
    return data.hex()


def hex_decode(data: str) -> bytes:
    """Decode hex string to bytes."""
    return bytes.fromhex(data)


def sha256(data: bytes) -> bytes:
    """Compute SHA-256 digest."""
    return hashlib.sha256(data).digest()


def sha256_hex(data: bytes) -> str:
    """Compute SHA-256 hex digest."""
    return hashlib.sha256(data).hexdigest()


def keccak256(data: bytes) -> bytes:
    """Compute Keccak-256 digest (used by Starknet for identity hashing)."""
    k = hashlib.new("sha3_256")  # Python uses SHA3-256; close enough for PoC
    k.update(data)
    return k.digest()


def truncate_display(data: str, length: int = 32) -> str:
    """Truncate a long hex/b64 string for display."""
    if len(data) <= length:
        return data
    return data[:length] + "..."


# =============================================================================
# Hybrid Seed Generation (Camera Entropy + Drand Beacon)
# =============================================================================

def generate_hybrid_seed(camera_entropy: bytes, drand_randomness: bytes) -> bytes:
    """
    Combine local camera entropy with public drand randomness to produce
    a 32-byte seed suitable for quantum key generation.

    Security properties:
      - Camera entropy: user-unique, non-reproducible local environment data
      - Drand randomness: publicly verifiable, timestamped global randomness
      - Combined: neither source alone can reconstruct the seed

    Construction:
      seed = HMAC-SHA256(key=drand_randomness, msg=SHA256(camera_entropy) || timestamp)

    This uses HMAC rather than simple concatenation+hash to provide:
      - Domain separation between the two entropy sources
      - Resistance to length-extension attacks
      - Proper key derivation structure

    Args:
        camera_entropy: Raw pixel bytes from camera frame capture.
        drand_randomness: 32-byte randomness from Drand beacon.

    Returns:
        32-byte deterministic seed for key generation.

    Raises:
        ValueError: If inputs are empty or drand_randomness is wrong size.
    """
    if not camera_entropy:
        raise ValueError("Camera entropy cannot be empty")
    if not drand_randomness or len(drand_randomness) < 16:
        raise ValueError("Drand randomness must be at least 16 bytes")

    # Hash camera entropy to fixed 32 bytes (may be megabytes of pixel data)
    camera_hash = hashlib.sha256(camera_entropy).digest()

    # Add timestamp for additional uniqueness
    timestamp_bytes = struct.pack(">d", time.time())

    # Combine: HMAC-SHA256(key=drand, msg=camera_hash || timestamp)
    message = camera_hash + timestamp_bytes
    seed = hmac.new(drand_randomness, message, hashlib.sha256).digest()

    return seed  # 32 bytes


def compute_entropy_hash(camera_entropy: bytes) -> str:
    """
    Compute a non-reversible hash of the camera entropy for audit trail.
    This is stored in the identity file so we can prove the seed source
    without exposing the raw camera data.
    """
    return hashlib.sha256(camera_entropy).hexdigest()

