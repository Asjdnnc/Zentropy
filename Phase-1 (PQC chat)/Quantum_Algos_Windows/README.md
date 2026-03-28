# Quantum-Safe Chat System 🛡️

A post-quantum cryptographic key exchange and encrypted chat system using **liboqs** (ML-KEM-768 + ML-DSA-44) and **AES-GCM**.

## 🚀 Features

- **Quantum-Safe Key Exchange:** Uses **Kyber768 (ML-KEM)** for key encapsulation.
- **Identity Verification:** Uses **Dilithium44 (ML-DSA)** for signing keys.
- **AES Encrypted Chat:** Messages are encrypted with **AES-GCM-256** using the shared secret.
- **Auto-Handshake:** Automatically finds the peer and establishes a secure channel.
- **Helper Scripts:** Easy `send_message.py` and `receive_message.py`.

## 📦 Prerequisites

1.  **Python 3.10+**
2.  **liboqs C Library** (Pre-built in `libhosdike/liboqs`)
3.  **Dependencies:**
    ```bash
    pip install fastapi uvicorn requests cryptography liboqs-python python-dotenv
    ```

---

## 🛠️ Step-by-Step Usage

### 1. Configuration (.env)

Create a file named `.env` in the `Quantum_Algos` directory (or rename `.env.example`).
**Edit the `.env` file** to match your network:

```ini
# Port for the server to listen on
SERVER_PORT=65432

# IP Address of the OTHER person (Friend's IP)
TARGET_RECEIVER_IP=192.168.1.34

# Path to liboqs library (Windows)
LIBOQS_DLL_PATH=C:/Users/shiva/OneDrive/Desktop/zentropy/libhosdike/liboqs/build/bin/liboqs.dll

# Path to liboqs library (Mac/Linux)
LIBOQS_DYLIB_PATH=/Users/adityakumar/liboqs/build/lib/liboqs.dylib

# Local server URL (for client scripts)
LOCAL_SERVER_URL=http://127.0.0.1

# --- HANDSHAKE ROLE ---
# One machine MUST be INITIATOR (starts connection)
# The other MUST be LISTENER (waits for connection)
HANDSHAKE_ROLE=INITIATOR
```

_(Ensure `TARGET_RECEIVER_IP` points to your friend's machine, and they point theirs to you)._

### 2. Set Roles (Critical!)

- **Computer A (You)**: Set `HANDSHAKE_ROLE=INITIATOR` in `.env`.
- **Computer B (Friend)**: Set `HANDSHAKE_ROLE=LISTENER` in `.env`.

### 3. Start the Secure Chat (Both Computers)

Both you and your friend must run this command in a terminal:

```bash
# Activate environment
./myenv/Scripts/activate

# Run the consolidated server & chat app
python server.py
```

**What happens?**

1.  The servers automatically generate keys.
2.  They find each other on the network.
3.  They exchange keys and derive a **Shared Secret**.
4.  You will see: `🔑 SHARED SECRET ESTABLISHED: ...`
5.  **Chat UI Activates**: You can type messages directly in this window.

### 3. Chatting 💬

Once the key is established:

- **Type a message** and press Enter to send.
- **Incoming messages** will appear automatically in the same window.
- Everything is encrypted with **AES-GCM-256** + **Kyber768**.\_

---

## 📂 File Structure

| File                 | Description                                                    |
| :------------------- | :------------------------------------------------------------- |
| `server.py`          | The main heart. Handles Key Gen, Handshake, and API endpoints. |
| `phase1.py`          | Core Cryptography (Kyber/Dilithium via liboqs).                |
| `phase2.py`          | AES-GCM Encryption Logic.                                      |
| `send_message.py`    | User-friendly script to send chats.                            |
| `receive_message.py` | User-friendly script to read chats.                            |

## ⚠️ Troubleshooting

- **"Connection Refused"**: Check firewalls! Ensure port `65432` is open.
- **"Shared Secret Missing"**: Wait for the servers to finish the handshake (look for the key in server logs).
- **"Address not valid"**: Make sure `server.py` is running on `0.0.0.0` but scripts connect to `127.0.0.1`.
- **"NameError: name 'oqs' is not defined"**: Ensure `server.py` has `import oqs`. This is fixed in the latest version.

## ⚙️ Technical Execution Flow

Here is exactly what happens when you run the system, step-by-step:

### 1️⃣ Server Startup (Computer A)

- **File:** `server.py`
- **Function:** `auto_initiate_handshake()` (triggered by `@app.on_event("startup")`)
- **Action:**
  1.  Calls `phase1.run_workflow()`:
      - Generates **Dilithium Identity Key**.
      - Fetches **Drand Randomness**.
      - Generates **Kyber Session Key** (Deterministically).
  2.  Spawns a background thread `enable_auto_send()`.
  3.  Tries to POST keys to `http://TARGET_IP:65432/handshake/offer`.

### 2️⃣ Handshake Request (Computer B)

- **File:** `server.py`
- **Function:** `handle_offer(payload)` (Endpoint: `/handshake/offer`)
- **Action:**
  1.  Receives Computer A's Public Keys.
  2.  Uses `oqs.KeyEncapsulation.encapsulate()` directly:
      - Generates a **Shared Secret** (AES Key).
      - Generates a **Ciphertext**.
  3.  POSTs the Ciphertext back to Computer A at `/decapsulate`.

### 3️⃣ Decapsulation (Computer A)

- **File:** `server.py`
- **Function:** `decapsulate(payload)` (Endpoint: `/decapsulate`)
- **Action:**
  1.  Calls `phase1.decapsulate_key_from_seed()`:
      - Re-creates the Private Key from the signature (using custom RNG).
      - Decapsulates Ciphertext -> **Shared Secret**.
  2.  Both computers now have the **SAME Shared Secret**.

### 4️⃣ Sending Messages

- **File:** `send_message.py` -> `server.py`
- **Function:** `send_chat(payload)` (Endpoint: `/chat/send`)
- **Action:**
  1.  Encrypts message using `phase2.SecureMessenger.encrypt()`.
  2.  POSTs encrypted data to Peer's `/chat/receive`.

### 5️⃣ Receiving Messages

- **File:** `server.py` -> `receive_message.py`
- **Function:** `receive_chat(payload)` (Endpoint: `/chat/receive`)
- **Action:**
  1.  Decrypts message using `phase2.SecureMessenger.decrypt()`.
  2.  Stores it in `RECEIVED_MESSAGES` list.
