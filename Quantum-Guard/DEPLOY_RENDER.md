# Deploy Quantum-Guard Backend On Render

This project is configured to deploy the backend from the `deployment` branch using `render.yaml`.

## What To Keep

- `.env.example`: local development template.
- `.env.production.example`: production template showing required keys.

These files are intentionally committed and are used as reference templates.

## What Not To Commit

- `.env`
- `.starkli/`
- `.venv/`, `.pytest_cache/`, `__pycache__/`
- frontend build output (`quantum_wallet_ui/frontend/dist/`)

## Render Deployment Steps

1. In Render, create a new Blueprint and connect this GitHub repo.
2. Select branch: `deployment`.
3. Render reads `render.yaml` and provisions:
   - `quantum-guard-backend` web service (Docker)
   - `quantum-guard-postgres` PostgreSQL
4. In Render dashboard, set secret env vars for the backend service:
   - `STARKNET_PRIVATE_KEY`
   - `STARKNET_ACCOUNT_ADDRESS`
   - `QUANTUMGUARD_MASTER_SECRET`
   - `BOOTSTRAP_SECRET`
5. Deploy and wait for the first build.
6. Confirm health check: `GET /api/v2/health`.

## Frontend Integration

Frontend stays outside Render (for example Vercel/Netlify).
Set frontend env var:

- `VITE_API_URL=https://<your-render-backend-domain>`

## Notes

- `docker/entrypoint.sh` starts both the Rust prover and FastAPI app.
- The entrypoint now auto-uses Render `PORT` if `API_PORT` is not set.
- Runtime local data path on Render is ephemeral; this config uses `/tmp/merkle_batches`.
