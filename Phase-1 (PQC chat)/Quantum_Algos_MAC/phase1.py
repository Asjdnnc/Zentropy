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
import cv2
import time
import ctypes
from ctypes import CDLL, POINTER, c_uint8, c_size_t, CFUNCTYPE, c_char_p, c_void_p, c_int, byref

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# =============================================================================
# 1. LOAD THE C LIBRARY (Windows & Mac Paths)
# =============================================================================
if platform.system() == "Windows":
    LIB_PATH = os.getenv("LIBOQS_DLL_PATH", r"C:\Users\shiva\OneDrive\Desktop\zentropy\libhosdike\liboqs\build\bin\liboqs.dll")
    
    LIBOQS_BUILD_DIR = os.path.dirname(LIB_PATH)
    PATH_TO_LIBOQS = LIB_PATH
    
    if os.path.exists(LIBOQS_BUILD_DIR):
        os.environ['PATH'] = LIBOQS_BUILD_DIR + os.pathsep + os.path.dirname(sys.executable) + os.pathsep + os.environ['PATH']
        try:
            os.add_dll_directory(LIBOQS_BUILD_DIR)
        except AttributeError:
            pass
else:
    PATH_TO_LIBOQS = os.getenv("LIBOQS_DYLIB_PATH", "/Users/adityakumar/liboqs/build/lib/liboqs.dylib")

try:
    lib = CDLL(PATH_TO_LIBOQS)
    print("✅ Successfully loaded liboqs v0.15.0+!")
except OSError as e:
    print(f"❌ Failed to load library: {e}")
    exit(1)

# =============================================================================
# 2. DEFINE CTYPED FUNCTIONS (Manual Wrappers)
# =============================================================================

# SIG Functions
lib.OQS_SIG_new.argtypes = [c_char_p]
lib.OQS_SIG_new.restype = c_void_p
lib.OQS_SIG_keypair.argtypes = [c_void_p, POINTER(c_uint8), POINTER(c_uint8)]
lib.OQS_SIG_keypair.restype = c_int
lib.OQS_SIG_sign.argtypes = [c_void_p, POINTER(c_uint8), POINTER(c_size_t), POINTER(c_uint8), c_size_t, POINTER(c_uint8)]
lib.OQS_SIG_sign.restype = c_int
lib.OQS_SIG_free.argtypes = [c_void_p]

# KEM Functions
lib.OQS_KEM_new.argtypes = [c_char_p]
lib.OQS_KEM_new.restype = c_void_p
lib.OQS_KEM_keypair.argtypes = [c_void_p, POINTER(c_uint8), POINTER(c_uint8)]
lib.OQS_KEM_keypair.restype = c_int
lib.OQS_KEM_encaps.argtypes = [c_void_p, POINTER(c_uint8), POINTER(c_uint8), POINTER(c_uint8)]
lib.OQS_KEM_encaps.restype = c_int
lib.OQS_KEM_decaps.argtypes = [c_void_p, POINTER(c_uint8), POINTER(c_uint8), POINTER(c_uint8)]
lib.OQS_KEM_decaps.restype = c_int
lib.OQS_KEM_free.argtypes = [c_void_p]

# RNG Functions
RNG_CALLBACK = CFUNCTYPE(None, POINTER(c_uint8), c_size_t)
lib.OQS_randombytes_custom_algorithm.argtypes = [RNG_CALLBACK]
lib.OQS_randombytes_custom_algorithm.restype = None
lib.OQS_randombytes_switch_algorithm.argtypes = [c_char_p]
lib.OQS_randombytes_switch_algorithm.restype = None

# =============================================================================
# 2.5. CAMERA ENTROPY FUNCTION
# =============================================================================
def capture_camera_entropy():
    """Captures a single frame and returns its hash for local entropy."""
    print("   📸 Turning on camera for entropy...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("⚠️ Camera not accessible. Falling back to system entropy.")
        return os.urandom(32)
    
    # Allow camera to adjust to light (warmup)
    for _ in range(5):
        cap.read() 
    
    ret, frame = cap.read()
    cap.release()
    
    if ret:
        print("   📸 Picture clicked!")
        # Use SHA-256 to condense image into 32 bytes of physical entropy
        frame_data = frame.tobytes()
        return hashlib.sha256(frame_data).digest()
    
    return os.urandom(32)


# =============================================================================
# 3. HELPER CLASSES
# =============================================================================

class ManualDilithiumSigner:
    def __init__(self, alg):
        self.handle = lib.OQS_SIG_new(alg.encode('utf-8'))
        if not self.handle:
            raise RuntimeError(f"Could not create OQS_SIG for {alg}")
        
        # Hardcoded sizes for ML-DSA-44 (Dilithium2)
        if alg == "ML-DSA-44":
            self.pk_len = 1312
            self.sk_len = 2560 
            self.sig_len = 2420
        else:
            raise ValueError(f"Unknown sizes for {alg}")

    def generate_keypair(self):
        pk = (c_uint8 * self.pk_len)()
        self.sk = (c_uint8 * self.sk_len)() 
        
        if lib.OQS_SIG_keypair(self.handle, pk, self.sk) != 0:
            raise RuntimeError("Dilithium Keypair generation failed")
        
        return bytes(pk)

    def sign(self, message: bytes):
        sig = (c_uint8 * self.sig_len)()
        sig_len = c_size_t(self.sig_len)
        msg_b = (c_uint8 * len(message)).from_buffer_copy(message)
        
        if lib.OQS_SIG_sign(self.handle, sig, byref(sig_len), msg_b, len(message), self.sk) != 0:
            raise RuntimeError("Dilithium Signing failed")
            
        return bytes(sig[:sig_len.value])

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): lib.OQS_SIG_free(self.handle)


class ManualKyberKeyGen:
    def __init__(self, alg):
        self.handle = lib.OQS_KEM_new(alg.encode('utf-8'))
        if not self.handle:
            raise RuntimeError(f"Could not create OQS_KEM for {alg}")
            
        # Hardcoded sizes for ML-KEM-768 (Kyber768)
        if alg == "ML-KEM-768":
            self.pk_len = 1184
            self.sk_len = 2400
            self.ct_len = 1088
            self.ss_len = 32
        else:
            raise ValueError(f"Unknown sizes for {alg}")

    def generate_keypair(self):
        pk = (c_uint8 * self.pk_len)()
        self.sk = (c_uint8 * self.sk_len)() 
        
        if lib.OQS_KEM_keypair(self.handle, pk, self.sk) != 0:
            raise RuntimeError("Kyber Keypair generation failed")
            
        return bytes(pk)

    def encapsulate(self, pk: bytes):
        """Generates a shared secret and encapsulates it for the given public key."""
        ct = (c_uint8 * self.ct_len)()
        ss = (c_uint8 * self.ss_len)()
        pk_b = (c_uint8 * len(pk)).from_buffer_copy(pk)
        
        if lib.OQS_KEM_encaps(self.handle, ct, ss, pk_b) != 0:
            raise RuntimeError("Kyber Encapsulation failed")
            
        return bytes(ct), bytes(ss)

    def decap_secret(self, ciphertext: bytes):
        """Decapsulates the shared secret using the internal private key."""
        ss = (c_uint8 * self.ss_len)()
        ct_b = (c_uint8 * len(ciphertext)).from_buffer_copy(ciphertext)
        
        if lib.OQS_KEM_decaps(self.handle, ss, ct_b, self.sk) != 0:
            raise RuntimeError("Kyber Decapsulation failed")
            
        return bytes(ss)

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): lib.OQS_KEM_free(self.handle)

# =============================================================================
# 4. CUSTOM RNG (Trojan Horse)
# =============================================================================
custom_seed_buffer = b""
custom_seed_offset = 0

def my_custom_rng(random_array_ptr, bytes_needed):
    global custom_seed_buffer, custom_seed_offset
    for i in range(bytes_needed):
        if custom_seed_offset < len(custom_seed_buffer):
            random_array_ptr[i] = custom_seed_buffer[custom_seed_offset]
            custom_seed_offset += 1
        else:
            random_array_ptr[i] = 0 

c_rng_callback = RNG_CALLBACK(my_custom_rng)

# =============================================================================
# ENTROPY SOURCE 1: DRAND (Public Beacon)
# =============================================================================
def get_drand_randomness():
    """Fetches verifiable randomness from the Drand public beacon."""
    try:
        # Using the default drand mainnet multibeam
        url = "https://api.drand.sh/52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971/public/latest"
        resp = requests.get(url, timeout=5).json()
        return bytes.fromhex(resp['randomness']), resp['round']
    except Exception as e:
        print(f"⚠️ Drand fetch failed ({e}). Using fallback system entropy.")
        # Fallback to system entropy if the network is down
        return os.urandom(32), 0


# =============================================================================
# NEW: CAMERA ENTROPY CAPTURE
# =============================================================================
def capture_camera_entropy():
    """Captures a single frame and returns its hash for local entropy."""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("⚠️ Camera not accessible. Falling back to system entropy.")
        return os.urandom(32)
    
    # Allow camera to adjust to light (warmup)
    for _ in range(5):
        cap.read() 
    
    ret, frame = cap.read()
    cap.release()
    
    if ret:
        # Use SHA-256 to condense image into 32 bytes of physical entropy
        frame_data = frame.tobytes()
        return hashlib.sha256(frame_data).digest()
    
    return os.urandom(32)

# =============================================================================
# MODIFIED: KEY GENERATION WORKFLOW (Sender Side)
# =============================================================================
def run_workflow():
    global custom_seed_buffer, custom_seed_offset
    custom_seed_buffer = b""
    custom_seed_offset = 0

    print(f"\n1. Initiating Integrated Dual-Source Entropy Handshake...")
    result = {}

    try:
        # A. Create Identity (Dilithium)
        with ManualDilithiumSigner(DILITHIUM_ALG) as signer:
            signer_pk = signer.generate_keypair()
            result['identity_pk'] = signer_pk.hex()
            
            # B. Gather Mixed Entropy
            # Source 1: Public drand beacon
            drand_bytes, round_num = get_drand_randomness()
            # Source 2: Local Camera snapshot
            camera_bytes = capture_camera_entropy()
            
            print(f"   [Source 1] Drand Round: {round_num}")
            print(f"   [Source 2] Camera Snapshot Captured.")
            result['drand_round'] = round_num
            result['drand_randomness'] = drand_bytes.hex()
            
            # C. Mix Entropy and Sign
            # We combine both sources so the key is unique to the device AND the time
            combined_entropy = hashlib.sha256(drand_bytes + camera_bytes).digest()
            print(f"   [Combined Seed] {combined_entropy.hex()[:16]}... (Mixed Drand + Camera)")
            
            print() # Spacer
            seed_signature = signer.sign(combined_entropy)
            
            print("   ✅ Signed Combined Seed with Identity Key.")
            print(f"   [Seed Signature] {seed_signature.hex()[:16]}...")
            result['seed_signature'] = seed_signature.hex()

            # D. Derive Deterministic Seed for Kyber
            shake = hashlib.shake_256()
            shake.update(seed_signature)
            custom_seed_buffer = shake.digest(64) 
            custom_seed_offset = 0                

            # E. Switch RNG to Deterministic Mode
            print(f"\n2. Switching RNG to Custom Callback (Deterministic)...")
            lib.OQS_randombytes_custom_algorithm(c_rng_callback)
            lib.OQS_randombytes_switch_algorithm(b"custom")

            # F. Generate Kyber Keys (Deterministic based on signed mixed entropy)
            print(f"\n3. Generating Session Key ({KYBER_ALG})...")
            with ManualKyberKeyGen(KYBER_ALG) as kem:
                kyber_pk = kem.generate_keypair()
                print(f"   Kyber Public Key: {kyber_pk.hex()[:32]}...")
                result['kyber_pk'] = kyber_pk.hex()

                # G. Switch RNG Back to System (Safety)
                lib.OQS_randombytes_switch_algorithm(b"system")
                print("   RNG switched back to system mode.")

                # H. Certify the Kyber Key
                cert_sig = signer.sign(kyber_pk)
                print(f"\n4. Certified Kyber PK.\n   Signature: {cert_sig.hex()[:32]}...")
                result['certification_signature'] = cert_sig.hex()
                
        print("\n🎉 Integrated cryptographic workflow complete!")
        return result

    except Exception as e:
        print(f"❌ Error during generation: {e}")
        try: lib.OQS_randombytes_switch_algorithm(b"system")
        except: pass
        raise e
# =============================================================================
# 6. KEY RECOVERY WORKFLOW (Decapsulation)
# =============================================================================
def decapsulate_key_from_seed(ciphertext_hex, seed_signature_hex):
    global custom_seed_buffer, custom_seed_offset
    
    print(f"\n🔓 DECAPSULATING: Re-creating private key from signature...")

    # 1. Re-create the Deterministic Seed
    seed_signature = bytes.fromhex(seed_signature_hex)
    shake = hashlib.shake_256()
    shake.update(seed_signature)
    custom_seed_buffer = shake.digest(64)
    custom_seed_offset = 0
    
    # 2. Hijack the RNG (Deterministic Mode)
    lib.OQS_randombytes_custom_algorithm(c_rng_callback)
    lib.OQS_randombytes_switch_algorithm(b"custom")
    
    shared_secret = None
    
    try:
        # 3. Re-Generate the Keypair
        with ManualKyberKeyGen(KYBER_ALG) as kem:
            _ = kem.generate_keypair()
            
            # 4. Decapsulate
            ciphertext = bytes.fromhex(ciphertext_hex)
            shared_secret = kem.decap_secret(ciphertext)
            
            print(f"✅ Decapsulation successful!")

    except Exception as e:
        print(f"❌ Decapsulation Failed: {e}")
        raise e
    finally:
        lib.OQS_randombytes_switch_algorithm(b"system")
        print("   RNG restored to system mode.")
        
    return shared_secret.hex()

if __name__ == "__main__":
    print("Running self-test...")
    data = run_workflow()
    print("Self-test complete.")