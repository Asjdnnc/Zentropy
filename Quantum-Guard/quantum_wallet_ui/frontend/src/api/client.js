/**
 * QuantumGuard API Client
 * =======================
 * Axios-based client for communicating with the FastAPI backend.
 * 
 * Development: FastAPI runs on http://localhost:8000
 * Production:  Served from the same origin (static build)
 */
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
    baseURL: API_BASE,
    timeout: 120000,  // 2 min for contract deployment
    headers: { 'Content-Type': 'application/json' },
});

// ─── Health ─────────────────────────────────────────────────────

export const getHealth = () => api.get('/health');

// ─── Wallet ─────────────────────────────────────────────────────

export const createWallet = (label = 'default', cameraPhoto = '') =>
    api.post('/wallet/create', { label, camera_photo: cameraPhoto });

export const getWalletInfo = (label = 'default') =>
    api.get('/wallet/info', { params: { label } });

export const listWallets = () => api.get('/wallet/list');

export const getWalletBalance = (label, forceRefresh = false) =>
    api.get(`/wallet/${label}/balance`, { params: { force_refresh: forceRefresh } });

export const deployWalletContract = (label) =>
    api.post(`/wallet/${label}/deploy`);

// ─── Transactions ───────────────────────────────────────────────

export const signTransaction = ({ to, amount, nonce, data, label }) =>
    api.post('/transaction/sign', { to, amount, nonce, data, label });

export const proveSignature = ({ message, signature, public_key }) =>
    api.post('/transaction/prove', { message, signature, public_key });

export const executeTransaction = ({ to, amount, nonce, data, label }) =>
    api.post('/transaction/execute', { to, amount, nonce, data, label });

// ─── Token Transfers ───────────────────────────────────────────

export const createTransfer = ({ label, to_address, amount_strk }) =>
    api.post('/transfer/create', { label, to_address, amount_strk });

export const executeTransfer = ({ label, to_address, amount_strk }) =>
    api.post('/transfer/execute', { label, to_address, amount_strk });

export const getTransferStatus = (starknetTxHash) =>
    api.get(`/transfer/${starknetTxHash}/status`);

// ─── Transaction History & Status ──────────────────────────────

export const getTransactionHistory = ({ label, status, limit, offset } = {}) =>
    api.get('/transaction/history', { params: { label, status, limit, offset } });

export const getTransaction = (txId) =>
    api.get(`/transaction/${txId}`);

export const getTransactionStatus = (txId) =>
    api.get(`/transaction/${txId}/status`);

export const getProofs = (limit = 50) =>
    api.get('/proofs', { params: { limit } });

// ─── Starknet ──────────────────────────────────────────────────

export const getContractStatus = () => api.get('/contract/status');

export const deployContract = (label = 'default') =>
    api.post('/contract/deploy', { label });

// ─── Merkle Audit Trail ────────────────────────────────────────

export const getAuditBatches = ({ limit, committed_only } = {}) =>
    api.get('/audit/batches', { params: { limit, committed_only } });

export const getAuditBatch = (batchId) =>
    api.get(`/audit/batch/${batchId}`);

export const getAuditProof = (txId) =>
    api.get(`/audit/proof/${txId}`);

export const forceCommitBatch = () =>
    api.post('/audit/force-commit');

export default api;
