import warnings
# Filter warnings to reduce noise for the user
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

from fastapi import FastAPI, HTTPException, Body, Request
import fastapi
import uvicorn
import threading
import phase1  # Import our refactored module
import phase3  # Import AES logic
import oqs     # Import oqs library directly

# GLOBAL SHARED SECRET (The Result of Handshake)
CURRENT_SHARED_SECRET = None
RECEIVED_MESSAGES = [] # In-memory storage for chat history


app = FastAPI(title="Quantum Safe KeyGen Server")

# Global lock to handle non-thread-safe globals in phase1.py
# (liboqs randomness callback uses global variables)
workflow_lock = threading.Lock()

@app.on_event("startup")
async def startup_banner():
    import socket
    try:
        # Best effort to find the LAN IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "127.0.0.1"

    print("\n" + "="*60)
    print(f"🚀 QUANTUM SAFE SERVER STARTED on http://{local_ip}:65432")
    print("="*60)
    print("👉 Send this to your friend (The Encapsulator):")
    print(f"""
curl -X POST http://{local_ip}:65432/decapsulate \\
  -H "Content-Type: application/json" \\
  -d '{{"ciphertext": "YOUR_CIPHERTEXT", "seed_signature": "YOUR_SEED_SIGNATURE"}}'
""")
    print("="*60 + "\n")

from dotenv import load_dotenv
import os

load_dotenv()

# IP of the OTHER machine (The Receiver/Buddy)
# Update this in .env!
TARGET_RECEIVER_IP = os.getenv("TARGET_RECEIVER_IP")
if not TARGET_RECEIVER_IP:
    raise ValueError("TARGET_RECEIVER_IP not set in .env")

SERVER_PORT = int(os.getenv("SERVER_PORT", 65432))

@app.on_event("startup")
async def auto_initiate_handshake():
    """
    On startup, check ROLE. If INITIATOR, generate keys and send.
    If LISTENER, just wait.
    """
    import time
    import requests
    
    role = os.getenv("HANDSHAKE_ROLE", "INITIATOR").upper()
    if role != "INITIATOR":
        print(f"\n🎧 ROLE: {role}. Waiting for the Initiator ({TARGET_RECEIVER_IP}) to connect...")
        return

    # 1. Generate Our Keys (Only if Initiator)
    print(f"\n⚡ ROLE: INITIATOR. Generating Identity & Sending to {TARGET_RECEIVER_IP}...")
    if not workflow_lock.acquire(timeout=10): return
    try:
        keys = phase1.run_workflow()
    finally:
        workflow_lock.release()
    
    # 2. Try to Send to Receiver
    print(f"📡 AUTO-SEND: Attempting to send keys to {TARGET_RECEIVER_IP}...")
    
    def enable_auto_send():
        retry_count = 0
        while retry_count < 10:
            try:
                # Use a session to ensure clean connection handling
                with requests.Session() as s:
                    url = f"http://{TARGET_RECEIVER_IP}:65432/handshake/offer"
                    print(f"   Attempt {retry_count+1}/10: POST {url}...")
                    # Crucial: Short timeout so it doesn't hang the thread
                    resp = s.post(url, json=keys, timeout=5)
                    if resp.status_code == 200:
                        print("✅ SUCCESS! Keys sent. Server is now FREE to receive your reply...")
                        return 
            except Exception as e:
                print(f"   Connection failed ({e}). Retrying in 5s...")
            
            time.sleep(5)
            retry_count += 1
        print("❌ Could not connect to receiver after 10 attempts.")

    # Run in background so we don't block server startup
    threading.Thread(target=enable_auto_send, daemon=True).start()

@app.post("/handshake/offer")
def handle_offer(payload: dict = Body(...), request: fastapi.Request = None):
    """
    Receiver Side:
    1. Accept Public Key + Signature.
    2. Encapsulate (Create Shared Secret).
    3. Send Ciphertext BACK to sender.
    """
    try:
        sender_ip = request.client.host
        print(f"\n📨 RECEIVED OFFER from {sender_ip}")
        
        kyber_pk = payload['kyber_pk']
        seed_sig = payload['seed_signature'] # We need to echo this back
        
        # 1. Encapsulate (We need a helper for this in phase1 or do it here)
        # To avoid duplicating code, we'll use oqs directly here or add helper to phase1.
        # Let's do it inline for simplicity but using phase1 constants.
        
        print("   Encapsulating Shared Secret...")
        with oqs.KeyEncapsulation(phase1.KYBER_ALG) as client_kem:
            pk_bytes = bytes.fromhex(kyber_pk)
            ciphertext, shared_secret = client_kem.encap_secret(pk_bytes)
            
        print(f"   Generated Secret: {shared_secret.hex()[:32]}...")
        
        # SAVE THE SECRET!
        global CURRENT_SHARED_SECRET
        CURRENT_SHARED_SECRET = shared_secret.hex()
        
        # 2. Send Back to Sender
        reply_url = f"http://{sender_ip}:65432/decapsulate"
        reply_payload = {
            "ciphertext": ciphertext.hex(),
            "seed_signature": seed_sig
        }
        
        print(f"   Replying to {reply_url}...")
        import requests
        requests.post(reply_url, json=reply_payload)
        print("✅ Reply Sent! Handshake Complete on this side.")
        
        return {"status": "accepted"}
        
    except Exception as e:
        print(f"❌ Handshake Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
def read_root():
    return {
        "status": "online",
        "message": "Quantum Safe Server is running",
        "endpoints": ["POST /generate_keys"]
    }

@app.post("/generate_keys")
def generate_keys():
    """
    Triggers the Dilithium + Kyber workflow to generate a new Identity and Session Key.
    Thread-safe execution.
    """
    # Acquire lock to prevent race conditions on phase1's global variables
    if not workflow_lock.acquire(timeout=10):
        raise HTTPException(status_code=503, detail="Server busy, try again later")
    
    try:
        # Run the workflow and capture the result
        result = phase1.run_workflow()
        return {
            "status": "success",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        workflow_lock.release()

@app.post("/decapsulate")
def decapsulate(payload: dict = Body(...)):
    """
    Completes the Key Exchange.
    Recovers the Shared Secret using the provided Ciphertext and Session ID (Seed Signature).
    """
    ciphertext = payload.get("ciphertext")
    seed_sign = payload.get("seed_signature")
    
    if not ciphertext or not seed_sign:
        raise HTTPException(status_code=400, detail="Missing 'ciphertext' or 'seed_signature'")

    # Acquire lock (RNG is global)
    if not workflow_lock.acquire(timeout=10):
        raise HTTPException(status_code=503, detail="Server busy")
    
    try:
        shared_secret_hex = phase1.decapsulate_key_from_seed(ciphertext, seed_sign)
        print("\n" + "="*40)
        print(f"🔑 SHARED SECRET ESTABLISHED: {shared_secret_hex}")
        print("="*40 + "\n")
        
        # SAVE THE SECRET!
        global CURRENT_SHARED_SECRET
        CURRENT_SHARED_SECRET = shared_secret_hex
        
        return {
            "status": "success",
            "message": "Key Exchange Complete",
            "shared_secret": shared_secret_hex 
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        workflow_lock.release()

@app.post("/chat/send")
def send_chat(payload: dict = Body(...)):
    """
    Encrypts a message and sends it to the other peer.
    Payload: {"message": "Hello World"}
    """
    if not CURRENT_SHARED_SECRET:
        raise HTTPException(status_code=400, detail="Handshake not completed yet!")
    
    msg = payload.get("message")
    if not msg: raise HTTPException(status_code=400, detail="Message empty")
    
    try:
        # 1. Encrypt
        messenger = phase3.SecureMessenger(CURRENT_SHARED_SECRET)
        nonce, ciphertext = messenger.encrypt(msg)
        
        # 2. Send to Peer
        # We assume the peer is on port 65432 (same as us)
        import requests
        target_ip = TARGET_RECEIVER_IP 
        
        url = f"http://{target_ip}:65432/chat/receive"
        print(f"📤 Sending encrypted msg to {url}...")
        
        requests.post(url, json={
            "nonce": nonce,
            "ciphertext": ciphertext
        }, timeout=5)
        
        return {"status": "sent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat/receive")
def receive_chat(payload: dict = Body(...), request: Request = None):
    """
    Receives encrypted message, decrypts it, and prints to console.
    """
    if not CURRENT_SHARED_SECRET:
        print(f"⚠️ Received generic message but no Shared Secret yet!")
        raise HTTPException(status_code=400, detail="Shared secret missing")
        
    try:
        nonce = payload['nonce']
        ciphertext = payload['ciphertext']
        sender = request.client.host
        
        messenger = phase3.SecureMessenger(CURRENT_SHARED_SECRET)
        plaintext = messenger.decrypt(nonce, ciphertext)
        
        # Store for retrieval
        RECEIVED_MESSAGES.append({
            "sender": sender,
            "message": plaintext
        })
        
        # PRINT TO CONSOLE DIRECTLY
        print(f"\n📩 {sender}: {plaintext}\n📤 You: ", end="", flush=True)
        
        return {"status": "read"}
        
        return {"status": "read"}
    except Exception as e:
        print(f"❌ Decryption Error: {e}")
        raise HTTPException(status_code=400, detail="Decryption failed")

@app.get("/chat/history")
def get_chat_history():
    """
    Returns all received decrypted messages.
    """
    return RECEIVED_MESSAGES

def chat_input_loop():
    """Reads user input and sends encrypted messages."""
    import time
    print("Waiting for server to start...", end="", flush=True)
    time.sleep(3) # Wait for uvicorn to likely start
    print("\n\n💬 QUANTUM CHAT ACTIVE. Type a message and press Enter.")
    
    while True:
        try:
            if not CURRENT_SHARED_SECRET:
                time.sleep(1)
                continue
                
            msg = input("📤 You: ")
            if not msg: continue
            
            # Encrypt
            messenger = phase3.SecureMessenger(CURRENT_SHARED_SECRET)
            nonce, ciphertext = messenger.encrypt(msg)
            
            # Send
            url = f"http://{TARGET_RECEIVER_IP}:{SERVER_PORT}/chat/receive"
            try:
                import requests
                requests.post(url, json={"nonce": nonce, "ciphertext": ciphertext}, timeout=5)
            except Exception as e:
                print(f"⚠️ Failed to send: {e}")
                
        except KeyboardInterrupt:
            print("Exiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    print("🚀 Starting Quantum Safe Server...")
    
    # Run Uvicorn in a separate thread
    server_thread = threading.Thread(target=uvicorn.run, args=(app,), kwargs={"host": "0.0.0.0", "port": SERVER_PORT, "log_level": "error"}, daemon=True)
    server_thread.start()
    
    # Run Chat Loop in Main Thread
    chat_input_loop()
