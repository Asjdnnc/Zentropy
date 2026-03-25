import os
import subprocess
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")
rpc = os.environ.get("STARKNET_RPC", "")
account = os.environ.get("STARKNET_ACCOUNT_ADDRESS", "")

print("RPC", rpc)
print("ACCOUNT", account)

for cmd in [
    ["starkli", "block-number", "--rpc", rpc],
    ["starkli", "account", "fetch", account, "--rpc", rpc, "--output", "/tmp/qg_account_refresh.json"],
]:
    print("CMD", " ".join(cmd))
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        print("EXIT", p.returncode)
        out = (p.stdout or "") + ("\n" if p.stdout and p.stderr else "") + (p.stderr or "")
        print(out[:1200])
    except Exception as e:
        print("EXC", repr(e))
