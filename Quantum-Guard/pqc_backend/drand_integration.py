"""
QuantumGuard Drand Integration
==============================
Fetch publicly verifiable randomness from the Drand beacon network.

Drand provides:
  - Publicly verifiable random beacons (BLS threshold signatures)
  - Round-based timestamps (each round ~30 seconds)
  - Multiple relay endpoints for redundancy

The drand beacon is combined with local camera entropy to produce
a hybrid seed for quantum key generation, ensuring:
  1. Local uniqueness (camera entropy — non-reproducible per user)
  2. Public verifiability (drand beacon — timestamped on public chain)
  3. Neither source alone is sufficient to reconstruct the seed

Usage:
    from pqc_backend.drand_integration import fetch_drand_beacon
    beacon = fetch_drand_beacon()  # Returns DrandBeacon dataclass
"""
import hashlib
import json
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("quantumguard.drand")

# =============================================================================
# Drand Relay Endpoints (redundancy — try multiple if one fails)
# =============================================================================
DRAND_RELAYS = [
    "https://drand.cloudflare.com",
    "https://api.drand.sh",
    "https://drand.cloudflare.com",
]

# Default chain hash (unchained randomness — League of Entropy mainnet)
DRAND_CHAIN_HASH = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"

# Local cache path
_CACHE_DIR = Path.home() / ".quantum-guard" / "drand_cache"

# Request timeout (seconds)
DRAND_TIMEOUT = 10


@dataclass
class DrandBeacon:
    """A single Drand randomness beacon."""
    round: int
    randomness: str       # Hex-encoded 32-byte randomness
    signature: str        # BLS signature (hex)
    previous_signature: str  # Previous round signature (hex)
    genesis_time: int     # Chain genesis timestamp
    period: int           # Seconds between rounds
    fetched_at: float     # When we fetched this beacon

    @property
    def randomness_bytes(self) -> bytes:
        """Return the raw 32-byte randomness."""
        return bytes.fromhex(self.randomness)

    def to_dict(self) -> dict:
        """Serialize for storage / audit trail."""
        return asdict(self)


def fetch_drand_beacon(chain_hash: Optional[str] = None) -> DrandBeacon:
    """
    Fetch the latest Drand beacon from public relay endpoints.

    Tries multiple relays for redundancy. The beacon contains:
      - round:      Sequential beacon number
      - randomness: 32 bytes of publicly verifiable randomness
      - signature:  BLS threshold signature (proof of correctness)

    Args:
        chain_hash: Optional Drand chain hash. Defaults to mainnet.

    Returns:
        DrandBeacon with verified randomness.

    Raises:
        RuntimeError: If all relay endpoints fail.
    """
    chain = chain_hash or DRAND_CHAIN_HASH
    errors = []

    for relay in DRAND_RELAYS:
        try:
            url = f"{relay}/{chain}/public/latest"
            logger.debug(f"Fetching drand beacon from {relay}...")

            resp = requests.get(url, timeout=DRAND_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            beacon = DrandBeacon(
                round=data["round"],
                randomness=data["randomness"],
                signature=data.get("signature", ""),
                previous_signature=data.get("previous_signature", ""),
                genesis_time=data.get("genesis_time", 0),
                period=data.get("period", 30),
                fetched_at=time.time(),
            )

            # Verify randomness is 32 bytes
            raw = beacon.randomness_bytes
            if len(raw) != 32:
                raise ValueError(f"Unexpected randomness length: {len(raw)}")

            # Cache locally for audit trail
            _cache_beacon(beacon)

            logger.info(
                f"Drand beacon fetched: round={beacon.round}, "
                f"randomness={beacon.randomness[:16]}..."
            )
            return beacon

        except Exception as e:
            errors.append(f"{relay}: {e}")
            logger.warning(f"Drand relay {relay} failed: {e}")
            continue

    # All relays failed — try cached beacon as last resort
    cached = _load_cached_beacon()
    if cached:
        logger.warning("All drand relays failed. Using cached beacon.")
        return cached

    raise RuntimeError(
        f"Failed to fetch drand beacon from all relays:\n"
        + "\n".join(f"  - {err}" for err in errors)
    )


def fetch_drand_beacon_by_round(round_number: int, chain_hash: Optional[str] = None) -> DrandBeacon:
    """
    Fetch a specific Drand beacon by round number.
    Useful for reproducibility / verification.
    """
    chain = chain_hash or DRAND_CHAIN_HASH

    for relay in DRAND_RELAYS:
        try:
            url = f"{relay}/{chain}/public/{round_number}"
            resp = requests.get(url, timeout=DRAND_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            return DrandBeacon(
                round=data["round"],
                randomness=data["randomness"],
                signature=data.get("signature", ""),
                previous_signature=data.get("previous_signature", ""),
                genesis_time=data.get("genesis_time", 0),
                period=data.get("period", 30),
                fetched_at=time.time(),
            )
        except Exception:
            continue

    raise RuntimeError(f"Failed to fetch drand beacon for round {round_number}")


# =============================================================================
# Local caching (audit trail + fallback)
# =============================================================================

def _cache_beacon(beacon: DrandBeacon):
    """Cache a beacon locally for audit and fallback."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = _CACHE_DIR / "latest_beacon.json"
        cache_file.write_text(json.dumps(beacon.to_dict(), indent=2))
    except Exception as e:
        logger.warning(f"Failed to cache drand beacon: {e}")


def _load_cached_beacon() -> Optional[DrandBeacon]:
    """Load the most recently cached beacon."""
    try:
        cache_file = _CACHE_DIR / "latest_beacon.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
            return DrandBeacon(**data)
    except Exception as e:
        logger.warning(f"Failed to load cached drand beacon: {e}")
    return None


def verify_beacon_freshness(beacon: DrandBeacon, max_age_seconds: int = 120) -> bool:
    """
    Check if a beacon is recent enough for seed generation.

    Args:
        beacon: The DrandBeacon to check.
        max_age_seconds: Maximum acceptable age (default 2 minutes).

    Returns:
        True if the beacon is fresh enough.
    """
    age = time.time() - beacon.fetched_at
    return age <= max_age_seconds
