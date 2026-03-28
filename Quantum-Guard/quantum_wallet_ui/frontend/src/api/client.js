/**
 * QuantumGuard API Client — v2
 * ==============================
 * Axios-based client for communicating with the FastAPI v2 backend.
 *
 * Auth: All requests (except /health and /api/v2/org/create) require
 *   Authorization: Bearer <api_key>
 *
 * Setup (call once after org creation / page load):
 *   setApiKey('your-org-api-key')
 *   setActiveUserId('some-user-uuid')
 */
import axios from 'axios';

const resolveApiBase = () => {
    const configured = (import.meta.env.VITE_API_URL || '').trim();
    if (configured) return configured;

    if (import.meta.env.DEV) {
        return 'http://localhost:8000';
    }

    // In production, require explicit VITE_API_URL. We fall back to relative calls.
    console.warn('[api] VITE_API_URL is not set; using relative API paths.');
    return '';
};

const API_BASE = resolveApiBase();
const V2 = '/api/v2';

const api = axios.create({
    baseURL: API_BASE,
    timeout: 120000,  // 2 min for contract-related calls
    headers: { 'Content-Type': 'application/json' },
});

// ─── Auth helpers (persisted in localStorage) ───────────────
export const setApiKey = (key) => localStorage.setItem('qg_api_key', key);
export const getApiKey = () => localStorage.getItem('qg_api_key') || '';
export const clearApiKey = () => localStorage.removeItem('qg_api_key');
export const hasApiKey = () => Boolean(getApiKey().trim());
export const setActiveUserId = (id) => localStorage.setItem('qg_user_id', id);
export const getActiveUserId = () => localStorage.getItem('qg_user_id') || '';
export const clearActiveUserId = () => localStorage.removeItem('qg_user_id');
export const getApiBase = () => API_BASE;

const isPublicV2Endpoint = (url = '') => {
    const normalized = String(url);
    return normalized.includes(`${V2}/health`) || normalized.includes(`${V2}/org/create`);
};

const resolveUserId = (userId) => String(userId || getActiveUserId() || '').trim();

const ensureUserId = (userId, endpointName) => {
    const uid = resolveUserId(userId);
    if (!uid) {
        throw new Error(`Missing user_id for ${endpointName}. Select or create a wallet first.`);
    }
    return uid;
};

// Extract readable error messages from Pydantic validation errors or HTTP exceptions
const extractErrorMessage = (errorData) => {
    if (!errorData) return 'Unknown error';

    const detail = errorData.detail;

    // If detail is a string (HTTPException), return it directly
    if (typeof detail === 'string') {
        return detail;
    }

    // If detail is an array (Pydantic validation errors), extract messages
    if (Array.isArray(detail)) {
        return detail
            .map(err => {
                if (typeof err === 'object' && err.msg) {
                    const loc = Array.isArray(err.loc) ? err.loc.join(' → ') : '';
                    return loc ? `${loc}: ${err.msg}` : err.msg;
                }
                return String(err);
            })
            .join('\n');
    }

    // Fallback
    return String(detail);
};

// Automatically attach Bearer token on every request
api.interceptors.request.use((config) => {
    const key = getApiKey();
    if (key) {
        config.headers['Authorization'] = `Bearer ${key}`;
    } else if (!isPublicV2Endpoint(config.url || '')) {
        throw new Error('Missing API key. Set VITE_API_KEY or call setApiKey before protected API calls.');
    }
    return config;
});

// Enhance error responses with readable messages
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            clearApiKey();
            clearActiveUserId();
        }
        if (error.response?.data) {
            error.readableMessage = extractErrorMessage(error.response.data);
        }
        return Promise.reject(error);
    }
);

// ─── Health ─────────────────────────────────────────────────────
export const getHealth = (options = {}) =>
    api.get(`${V2}/health`, { signal: options.signal });

// ─── Organisation (bootstrap) ───────────────────────────────────
export const createOrg = ({ org_name, admin_email, bootstrap_secret }) =>
    api.post(`${V2}/org/create`, { org_name, admin_email, bootstrap_secret });

export const getOrgDetails = (options = {}) =>
    api.get(`${V2}/org`, { signal: options.signal });

// ─── Users / Wallets ────────────────────────────────────────────

/**
 * Register a new user + wallet.
 * Body: { email, username }
 * Returns: { user_id, wallet_id, contract_address, public_key, public_key_hash, seed_phrase }
 * Seed phrase is shown ONCE.
 */
export const createWallet = ({ email, username }) =>
    api.post(`${V2}/users/register`, { email, username });

/**
 * Get wallet details for a user (includes balance & deployment status).
 * @param {string} userId - user_id or label (defaults to localStorage active user)
 */
export const getWalletInfo = (userId = getActiveUserId(), options = {}) => {
    const uid = ensureUserId(userId, 'getWalletInfo');
    return api.get(`${V2}/users/${encodeURIComponent(uid)}/wallet`, { signal: options.signal });
};

export const getDeploymentStatus = (userId = getActiveUserId(), options = {}) => {
    const uid = ensureUserId(userId, 'getDeploymentStatus');
    return api.get(`${V2}/users/${encodeURIComponent(uid)}/deployment-status`, { signal: options.signal });
};

/**
 * Get wallet balance for a user. Returns same payload as getWalletInfo.
 * @param {string} userId - user_id or label (defaults to localStorage active user)
 */
export const getWalletBalance = (userId = getActiveUserId(), options = {}) => {
    const uid = ensureUserId(userId, 'getWalletBalance');
    return api.get(`${V2}/users/${encodeURIComponent(uid)}/wallet`, { signal: options.signal });
};

/**
 * List all users in the organisation.
 * Response keys match what WalletContext expects via `wallets` array.
 */
export const listWallets = (limit = 50, offset = 0, options = {}) =>
    api.get(`${V2}/users`, { params: { limit, offset }, signal: options.signal });

// ─── Transactions ───────────────────────────────────────────────

/**
 * Full transfer pipeline: sign → prove → batch → Starknet submit.
 * Body: { user_id or label, to_address, amount_strk }
 * (label is aliased to user_id for backwards compatibility)
 */
export const executeTransfer = ({ user_id, label, to_address, amount_strk }) =>
    api.post(`${V2}/transactions/transfer`, {
        user_id: ensureUserId(user_id || label, 'executeTransfer'),
        to_address,
        amount_strk,
    });

// Alias for backwards compat with pages that call createTransfer
export const createTransfer = executeTransfer;

export const getTransaction = (txId, options = {}) =>
    api.get(`${V2}/transactions/${txId}`, { signal: options.signal });

export const getTransactionStatus = (txId, options = {}) =>
    api.get(`${V2}/transactions/${txId}`, { signal: options.signal });

/**
 * Transaction history for a user.
 * @param {Object} params - { user_id?, limit?, offset? }
 */
export const getTransactionHistory = ({ user_id, limit = 50, offset = 0, signal } = {}) => {
    const uid = ensureUserId(user_id, 'getTransactionHistory');
    return api.get(`${V2}/users/${encodeURIComponent(uid)}/transactions`, {
        params: { limit, offset },
        signal,
    });
};


// ─── Merkle Batches / Audit ─────────────────────────────────────

export const getAuditBatches = ({ limit = 50, offset = 0, signal } = {}) =>
    api.get(`${V2}/batches`, { params: { limit, offset }, signal });

export const getAuditBatch = (batchId, options = {}) =>
    api.get(`${V2}/batches/${batchId}`, { signal: options.signal });

export const getAuditProof = (txId, options = {}) =>
    api.get(`${V2}/proof/${txId}`, { signal: options.signal });

export const forceCommitBatch = () =>
    api.post(`${V2}/batches/force-finalize`);

// ─── Contract / Prover status ───────────────────────────────────
// v2 exposes no dedicated /contract/status; health endpoint covers it.
export const getContractStatus = (options = {}) =>
    getHealth(options).then((res) => ({
        ...res,
        data: {
            ...res.data,
            deployed: res.data?.status === 'ok',
        },
    }));

// ─── Legacy stubs (kept so pages that import them don't crash) ──
export const signTransaction = () => Promise.resolve({ data: {} });
export const proveSignature = () => Promise.resolve({ data: {} });
export const executeTransaction = executeTransfer;
export const deployWalletContract = (userId, options = {}) => {
    const uid = ensureUserId(userId, 'deployWalletContract');
    return api.post(`${V2}/users/${encodeURIComponent(uid)}/deployment/retry`, {}, { signal: options.signal });
};
export const deployContract = () => Promise.resolve({ data: {} });
export const getProofs = (limit = 50) => getAuditBatches({ limit });
export const getTransferStatus = getTransactionStatus;

export default api;
