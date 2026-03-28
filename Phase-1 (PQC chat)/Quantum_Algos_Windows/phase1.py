# =============================================================================
# CONFIGURATION
# =============================================================================
# ML-KEM-768: NIST's standardized post-quantum Key Encapsulation Mechanism
KYBER_ALG = "ML-KEM-768"
# ML-DSA-44: NIST's standardized post-quantum Digital Signature Algorithm
DILITHIUM_ALG = "ML-DSA-44"

import platform
import os
import sys
import hashlib
import requests
import ctypes
from ctypes import CDLL, POINTER, c_uint8, c_size_t, CFUNCTYPE, c_char_p

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# =============================================================================
# 1. LOAD THE C LIBRARY (Windows & Mac Paths)
# =============================================================================
if platform.system() == "Windows":
    # ⚠️ CHECK THIS PATH: Verify it matches your friend's actual folder structure
    # Use env var - NO FALLBACK (User must configure .env)
    LIB_PATH = os.getenv("LIBOQS_DLL_PATH")
    if not LIB_PATH:
        raise ValueError("LIBOQS_DLL_PATH not set in .env file")
    
    # We need the directory to add to PATH
    LIBOQS_BUILD_DIR = os.path.dirname(LIB_PATH)
    PATH_TO_LIBOQS = LIB_PATH
    
    # Add to PATH so Python can find dependent DLLs
    if os.path.exists(LIBOQS_BUILD_DIR):
        os.environ['PATH'] = LIBOQS_BUILD_DIR + os.pathsep + os.path.dirname(sys.executable) + os.pathsep + os.environ['PATH']
        try:
            os.add_dll_directory(LIBOQS_BUILD_DIR)
        except AttributeError:
            pass
else:
    # Default for macOS/Linux (Update if needed)
    PATH_TO_LIBOQS = os.getenv("LIBOQS_DYLIB_PATH", "/Users/adityakumar/liboqs/build/lib/liboqs.dylib")

try:
    import oqs
except ImportError:
    pass 

try:
    lib = CDLL(PATH_TO_LIBOQS)
    print("✅ Successfully loaded liboqs v0.15.0+!")
except OSError as e:
    print(f"❌ Failed to load library: {e}")
    exit(1)

# =============================================================================
# 2. DEFINE CUSTOM RNG CALLBACK (The "Trojan Horse")
# =============================================================================
RNG_CALLBACK = CFUNCTYPE(None, POINTER(c_uint8), c_size_t)

lib.OQS_randombytes_custom_algorithm.argtypes = [RNG_CALLBACK]
lib.OQS_randombytes_custom_algorithm.restype = None

lib.OQS_randombytes_switch_algorithm.argtypes = [c_char_p]
lib.OQS_randombytes_switch_algorithm.restype = None

# Global buffers for deterministic generation
custom_seed_buffer = b""
custom_seed_offset = 0

def my_custom_rng(random_array_ptr, bytes_needed):
    """
    Feeds our pre-calculated seed bytes into the C library 
    instead of using system randomness.
    """
    global custom_seed_buffer, custom_seed_offset
    for i in range(bytes_needed):
        if custom_seed_offset < len(custom_seed_buffer):
            random_array_ptr[i] = custom_seed_buffer[custom_seed_offset]
            custom_seed_offset += 1
        else:
            random_array_ptr[i] = 0 

c_rng_callback = RNG_CALLBACK(my_custom_rng)

# =============================================================================
# 3. HELPER FUNCTIONS
# =============================================================================
def get_drand_randomness():
    """Fetches verifiable randomness from Drand."""
    try:
        url = "https://api.drand.sh/52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971/public/latest"
        resp = requests.get(url, timeout=5).json()
        return bytes.fromhex(resp['randomness']), resp['round']
    except Exception as e:
        print(f"⚠️ Drand fetch failed ({e}). Using fallback entropy.")
        return os.urandom(32), 0

# =============================================================================
# 4. KEY GENERATION WORKFLOW (Sender Side)
# =============================================================================
def run_workflow():
    global custom_seed_buffer, custom_seed_offset
    custom_seed_buffer = b""
    custom_seed_offset = 0

    print(f"\n1. Generating Identity Key ({DILITHIUM_ALG})...")
    result = {}

    try:
        # A. Create Identity (Dilithium)
        with oqs.Signature(DILITHIUM_ALG) as signer:
            signer_pk = signer.generate_keypair()
            result['identity_pk'] = signer_pk.hex()
            
            # B. Get Randomness & Sign it
            drand_bytes, round_num = get_drand_randomness()
            print(f"   Fetched Drand Round: {round_num}")
            result['drand_round'] = round_num
            result['drand_randomness'] = drand_bytes.hex()
            
            seed_signature = signer.sign(drand_bytes)
            print("   Signed Drand value with Dilithium.")
            result['seed_signature'] = seed_signature.hex()

            # C. Derive Deterministic Seed
            shake = hashlib.shake_256()
            shake.update(seed_signature)
            custom_seed_buffer = shake.digest(64) 
            custom_seed_offset = 0                

            # D. Switch RNG to Deterministic Mode
            print(f"\n2. Switching RNG to Custom Callback (Deterministic)...")
            lib.OQS_randombytes_custom_algorithm(c_rng_callback)
            lib.OQS_randombytes_switch_algorithm(b"custom")

            # E. Generate Kyber Keys (Deterministic)
            print(f"\n3. Generating Session Key ({KYBER_ALG})...")
            with oqs.KeyEncapsulation(KYBER_ALG) as kem:
                kyber_pk = kem.generate_keypair()
                print(f"   Kyber Public Key: {kyber_pk.hex()[:32]}...")
                result['kyber_pk'] = kyber_pk.hex()

                # F. Switch RNG Back to System (Safety)
                lib.OQS_randombytes_switch_algorithm(b"system")
                print("   RNG switched back to system mode.")

                # G. Certify the Kyber Key
                cert_sig = signer.sign(kyber_pk)
                print(f"\n4. Certified Kyber PK.\n   Signature: {cert_sig.hex()[:32]}...")
                result['certification_signature'] = cert_sig.hex()
                
        print("\n🎉 Cryptographic workflow complete!")
        return result

    except Exception as e:
        print(f"❌ Error during generation: {e}")
        try: lib.OQS_randombytes_switch_algorithm(b"system")
        except: pass
        raise e

# =============================================================================
# 5. KEY RECOVERY WORKFLOW (Decapsulation)
# =============================================================================
def decapsulate_key_from_seed(ciphertext_hex, seed_signature_hex):
    """
    Re-derives the Kyber Secret Key from the seed_signature 
    and uses it to decapsulate the ciphertext.
    """
    global custom_seed_buffer, custom_seed_offset
    
    print(f"\n🔓 DECAPSULATING: Re-creating private key from signature...")

    # 1. Re-create the Deterministic Seed
    seed_signature = bytes.fromhex(seed_signature_hex)
    shake = hashlib.shake_256()
    shake.update(seed_signature)
    custom_seed_buffer = shake.digest(64)
    custom_seed_offset = 0
    
    # 2. Hijack the RNG (Deterministic Mode)
    # This forces Kyber to generate the EXACT same private key as before
    lib.OQS_randombytes_custom_algorithm(c_rng_callback)
    lib.OQS_randombytes_switch_algorithm(b"custom")
    
    shared_secret = None
    
    try:
        # 3. Re-Generate the Keypair (We only need the Private Key from this)
        with oqs.KeyEncapsulation(KYBER_ALG) as kem:
            # generate_keypair() returns the Public Key, but stores Private Key internally
            _ = kem.generate_keypair()
            
            # 4. Use the Internal Private Key to Open the Box
            ciphertext = bytes.fromhex(ciphertext_hex)
            
            # --- FIXED: Use 'decap_secret' instead of 'decapsulate' ---
            shared_secret = kem.decap_secret(ciphertext)
            
            print(f"✅ Decapsulation successful!")

    except Exception as e:
        print(f"❌ Decapsulation Failed: {e}")
        raise e
    finally:
        # 5. RESTORE SAFETY (Crucial!)
        # Switch back to system RNG immediately
        lib.OQS_randombytes_switch_algorithm(b"system")
        print("   RNG restored to system mode.")
        
    return shared_secret.hex()

if __name__ == "__main__":
    # Self-test if run directly
    print("Running self-test...")
    data = run_workflow()
    print("Self-test complete.")