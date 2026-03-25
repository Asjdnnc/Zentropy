import os
import sqlite3

DB_PATH = "/home/shubham/.quantum-guard/live_demo_v2.db"

print("DB_EXISTS", os.path.exists(DB_PATH), DB_PATH)
if not os.path.exists(DB_PATH):
    raise SystemExit(0)

con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row
cur = con.cursor()

rows = cur.execute(
    """
    SELECT account_id, wallet_id, account_address, deployment_status,
           deployment_tx_hash, deployment_error_message, deployment_attempts, updated_at
    FROM accounts
    WHERE lower(coalesce(deployment_status, '')) != 'deployed'
    ORDER BY coalesce(updated_at, 0) DESC
    LIMIT 10
    """
).fetchall()

print("NON_DEPLOYED_COUNT", len(rows))
for row in rows:
    print(dict(row))

events = cur.execute(
    """
    SELECT action, entity_id, details, created_at
    FROM audit_logs
    WHERE action IN ('account_deploy_failed', 'account_deployed')
    ORDER BY created_at DESC
    LIMIT 12
    """
).fetchall()

print("DEPLOY_EVENTS", len(events))
for event in events:
    print(dict(event))

con.close()
