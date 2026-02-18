# Quantum-Safe Chat System 🛡️

A post-quantum cryptographic key exchange and encrypted chat system using **liboqs** (ML-KEM-768 + ML-DSA-44) and **AES-GCM**.

## 🚀 Features

- **Quantum-Safe Key Exchange:** Uses **Kyber768 (ML-KEM)** for key encapsulation.
- **Identity Verification:** Uses **Dilithium44 (ML-DSA)** for signing keys.
- **Mixed Entropy:** Combines **Drand** public beacon + **Camera** snapshot for high-quality randomness.
- **AES Encrypted Chat:** Messages are encrypted with **AES-GCM-256** using the shared secret.
- **Auto-Handshake:** Automatically finds the peer and establishes a secure channel.
- **Helper Scripts:** Easy `send_message.py` and `receive_message.py`.

## 📦 Prerequisites

1.  **Python 3.10+**
2.  **CMake** (for building liboqs)
3.  **Dependencies:** `pip install -r requirements.txt`

## 🚀 Quick Start (Mac/Linux)

### Automatic Setup (Recommended)

We have provided a setup script that automates the entire process:
1.  Installs Python dependencies.
2.  Builds the `liboqs` C library from source.
3.  Configures your `.env` file with the correct library path.

**Run the following command in your terminal:**

```bash
bash setup.sh
```

After the script finishes:
1.  Open the generate `.env` file.
2.  Update `TARGET_RECEIVER_IP` to your friend's IP address.
3.  Update `HANDSHAKE_ROLE` (One person must be `INITIATOR`, the other `LISTENER`).

### Manual Setup (Mac)

If you prefer to set up manually:

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    brew install cmake ninja  # Required for building liboqs
    ```

2.  **Build liboqs:**
    ```bash
    bash build_liboqs.sh
    ```
    This will create `liboqs/build/lib/liboqs.dylib`.

3.  **Configure Environment:**
    - Copy `.env.example` to `.env`.
    - Set `LIBOQS_DYLIB_PATH` to the absolute path of the built `liboqs.dylib`.
    - Set `SERVER_PORT`, `TARGET_RECEIVER_IP`, etc.

---

## 🏃 Run the Project

Once the setup is complete, you can start the secure chat server.

1.  **Activate your environment** (if you created one manually, otherwise skip):
    ```bash
    # source venv/bin/activate
    ```

2.  **Run the Server:**
    ```bash
    python server.py
    ```

3.  **Repeat on the second computer.**

### What happens next?
1.  The servers automatically generate keys.
2.  They find each other on the network.
3.  They exchange keys and derive a **Shared Secret**.
4.  **Chat UI Activates**: You can type messages directly in the terminal window.

---

## 📂 File Structure

| File                 | Description                                                    |
| :------------------- | :------------------------------------------------------------- |
| `server.py`          | The main heart. Handles Key Gen, Handshake, and API endpoints. |
| `phase1.py`          | Core Cryptography (Kyber/Dilithium via liboqs types).          |
| `phase2.py`          | AES-GCM Encryption Logic (SecureMessenger).                    |
| `setup.sh`           | Automated setup script for Mac/Linux.                          |
| `build_liboqs.sh`    | Script to build liboqs C library.                              |
| `requirements.txt`   | Python dependencies.                                           |

## ⚠️ Troubleshooting

- **"Connection Refused"**: Check firewalls! Ensure port `65432` is open.
- **"Shared Secret Missing"**: Wait for the servers to finish the handshake (look for the key in server logs).
- **"Address not valid"**: Make sure `server.py` is running on `0.0.0.0` but scripts connect to `127.0.0.1`.

## ⚙️ Technical Execution Flow

Here is exactly what happens when you run the system, step-by-step:

### 1️⃣ Server Startup (Computer A)

- **File:** `server.py`
- **Function:** `auto_initiate_handshake()` (triggered by `@app.on_event("startup")`)
- **Action:**
  1.  Calls `phase1.run_workflow()`:
      - Generates **Dilithium Identity Key**.
      - Fetches **Drand Randomness**.
      - **Captures Camera Snapshot** (Entropy).
      - Combines entropy sources -> **Combined Seed**.
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
  1.  Encrypts message using `phase3.SecureMessenger.encrypt()`.
  2.  POSTs encrypted data to Peer's `/chat/receive`.

### 5️⃣ Receiving Messages

- **File:** `server.py` -> `receive_message.py`
- **Function:** `receive_chat(payload)` (Endpoint: `/chat/receive`)
- **Action:**
  1.  Decrypts message using `phase3.SecureMessenger.decrypt()`.
  2.  Stores it in `RECEIVED_MESSAGES` list.
