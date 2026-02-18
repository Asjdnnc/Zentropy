import os
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    print("❌ 'cryptography' library not found. Run 'pip install cryptography'")
    raise ImportError

class SecureMessenger:
    def __init__(self, shared_secret_hex):
        """
        Initialize with the Shared Secret (HEX string) derived from Phase 1/2.
        """
        if not shared_secret_hex:
            raise ValueError("Shared Secret cannot be empty")
        
        # AES-GCM-256 requires a 32-byte key
        key_bytes = bytes.fromhex(shared_secret_hex)
        
        # If the key is longer (e.g., Kyber output might be different), truncate or hash it.
        # Kyber768 shared secret is usually 32 bytes (256 bits).
        if len(key_bytes) != 32:
            print(f"⚠️ Shared secret is {len(key_bytes)} bytes. Adjusting to 32 bytes.")
            # Simple truncation or padding (In production, use HKDF)
            if len(key_bytes) > 32:
                key_bytes = key_bytes[:32]
            else:
                key_bytes = key_bytes.ljust(32, b'\0')

        self.aesgcm = AESGCM(key_bytes)

    def encrypt(self, plaintext: str):
        """
        Encrypts a string message.
        Returns: (nonce_hex, ciphertext_hex)
        """
        # 1. Generate a unique Nonce (12 bytes is standard for GCM)
        nonce = os.urandom(12)
        
        # 2. Encrypt
        data = plaintext.encode('utf-8')
        ciphertext = self.aesgcm.encrypt(nonce, data, None)
        
        return nonce.hex(), ciphertext.hex()

    def decrypt(self, nonce_hex: str, ciphertext_hex: str):
        """
        Decrypts a message.
        Returns: plaintext string
        Raises: InvalidTag if tampering detected.
        """
        nonce = bytes.fromhex(nonce_hex)
        ciphertext = bytes.fromhex(ciphertext_hex)
        
        plaintext_bytes = self.aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext_bytes.decode('utf-8')
