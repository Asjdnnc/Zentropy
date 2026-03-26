import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { listWallets, getWalletBalance, executeTransfer, getTransferStatus, getWalletInfo, setActiveUserId } from "../api/client";
import { useWallet } from "../context/WalletContext";
import Card from "../components/Card";
import Button from "../components/Button";

export default function SendTokens() {
    const [searchParams] = useSearchParams();
    const initialWallet = searchParams.get("wallet") || "";
    const { refreshAll } = useWallet();

    const [wallets, setWallets] = useState([]);
    const [balances, setBalances] = useState({});
    const [form, setForm] = useState({
        user_id: initialWallet,
        to_address: "",
        amount_strk: "",
    });
    const [sending, setSending] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [txStatus, setTxStatus] = useState(null);
    const [polling, setPolling] = useState(false);
    const [pollTimedOut, setPollTimedOut] = useState(false);
    const pollAbortRef = useRef(null);

    const balanceText = (b) => b?.balance_display || b?.balance_strk || "0.000000";

    const isAbortError = (err) =>
        err?.name === "AbortError" ||
        err?.code === "ERR_CANCELED" ||
        /aborted|canceled/i.test(String(err?.message || ""));

    const fetchWallets = useCallback(async (options = {}) => {
        try {
            const res = await listWallets(50, 0, { signal: options.signal });
            const users = res.data.users || res.data.wallets || [];
            const enriched = await Promise.all(
                users.map(async (u) => {
                    const userId = u.user_id || u.label;
                    if (!userId) return null;
                    try {
                        const walletRes = await getWalletInfo(userId, { signal: options.signal });
                        return {
                            label: userId,
                            user_id: userId,
                            username: u.username || u.email || userId,
                            ...walletRes.data,
                        };
                    } catch {
                        return null;
                    }
                })
            );
            const w = enriched.filter(Boolean).filter(
                (wallet) => wallet.contract_address && wallet.deployment_status === "deployed"
            );
            setWallets(w);

            // Auto-select first if no wallet specified
            if (!form.user_id && w.length > 0) {
                setForm((prev) => ({ ...prev, user_id: w[0].user_id }));
            }

            // Fetch balances
            const balanceResults = await Promise.all(
                w.map((wallet) =>
                    getWalletBalance(wallet.user_id, { signal: options.signal })
                        .then((r) => ({ user_id: wallet.user_id, data: r.data }))
                        .catch(() => null)
                )
            );
            const newBalances = {};
            balanceResults.forEach((b) => {
                if (b) newBalances[b.user_id] = b.data;
            });
            setBalances(newBalances);
        } catch (err) {
            if (isAbortError(err)) {
                return;
            }
            // API offline
        }
    }, [form.user_id]);

    useEffect(() => {
        const abortController = new AbortController();
        fetchWallets({ signal: abortController.signal });
        return () => abortController.abort();
    }, [fetchWallets]);

    useEffect(() => {
        return () => {
            if (pollAbortRef.current) {
                pollAbortRef.current.abort();
                pollAbortRef.current = null;
            }
        };
    }, []);

    function handleChange(e) {
        const { name, value } = e.target;
        if (name === "user_id") {
            setActiveUserId(value);
        }
        setForm({ ...form, [name]: value });
    }

    function validateAddress(addr) {
        const value = String(addr || "").trim();
        if (!/^0x[0-9a-fA-F]{1,64}$/.test(value)) return false;
        const body = value.slice(2).replace(/^0+/, "");
        return body.length > 0;
    }

    async function handleSubmit(e) {
        e.preventDefault();
        setError(null);
        setResult(null);
        setTxStatus(null);

        if (!form.user_id) {
            setError("Please select a wallet");
            return;
        }
        if (!validateAddress(form.to_address)) {
            setError("Invalid recipient address. Must be 0x followed by hex characters.");
            return;
        }
        const amount = parseFloat(form.amount_strk);
        if (isNaN(amount) || amount <= 0) {
            setError("Amount must be greater than 0");
            return;
        }
        if (!/^\d+(\.\d{1,6})?$/.test(String(form.amount_strk).trim())) {
            setError("Amount supports up to 6 decimal places.");
            return;
        }
        const available = parseFloat(selectedBalance?.balance_display || selectedBalance?.balance_strk || "0");
        if (!Number.isNaN(available) && amount > available) {
            setError("Insufficient balance for this transfer.");
            return;
        }

        setSending(true);
        setPollTimedOut(false);

        try {
            setActiveUserId(form.user_id);
            const res = await executeTransfer({
                user_id: form.user_id,
                to_address: form.to_address,
                amount_strk: amount,
            });
            setResult(res.data);

            // Refresh balances after transfer
            await refreshAll();
            await fetchWallets();

            // Poll for confirmation if we got a tx hash
            if (res.data.tx_id) {
                pollTxStatus(res.data.tx_id);
            }
        } catch (err) {
            setError(
                err.readableMessage ||
                err.response?.data?.detail ||
                err.message ||
                "Transfer failed"
            );
        } finally {
            setSending(false);
        }
    }

    async function pollTxStatus(txId, options = {}) {
        if (pollAbortRef.current) {
            pollAbortRef.current.abort();
        }

        const maxAttempts = options.maxAttempts || 30;
        const intervalMs = options.intervalMs || 3000;
        const controller = new AbortController();
        pollAbortRef.current = controller;
        setPolling(true);
        setPollTimedOut(false);
        let terminalStatus = null;

        for (let i = 0; i < maxAttempts; i++) {
            if (controller.signal.aborted) {
                setPolling(false);
                return;
            }
            await new Promise((r) => setTimeout(r, intervalMs));
            try {
                const res = await getTransferStatus(txId, { signal: controller.signal });
                setTxStatus(res.data);
                if (res.data.status === "confirmed" || res.data.status === "rejected") {
                    terminalStatus = res.data.status;
                    setPolling(false);
                    break;
                }
            } catch (err) {
                if (isAbortError(err)) {
                    setPolling(false);
                    return;
                }
                setPolling(false);
                break;
            }
        }

        if (!terminalStatus) {
            setPollTimedOut(true);
        }
        setPolling(false);
    }

    const selectedBalance = balances[form.user_id];

    return (
        <div className="space-y-8 animate-fade-in">
            <div>
                <h1 className="text-3xl font-bold font-orbitron text-white">
                    Send STRK
                </h1>
                <p className="text-gray-400 mt-1">
                    Transfer tokens using quantum-resistant signatures (ML-DSA-44)
                </p>
            </div>

            {wallets.length === 0 ? (
                <Card variant="default" className="text-center py-12">
                    <p className="text-gray-400 mb-4">
                        No deployed wallets found. Create a wallet first.
                    </p>
                    <Link
                        to="/wallet"
                        className="text-neon-cyan hover:underline font-orbitron text-sm"
                    >
                        Create Wallet
                    </Link>
                </Card>
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                    {/* Transfer Form */}
                    <Card variant="neon" title="Transfer Details">
                        <form onSubmit={handleSubmit} className="space-y-5">
                            {/* Wallet Selector */}
                            <div>
                                <label className="block text-xs font-orbitron text-gray-400 mb-2 uppercase">
                                    From Wallet
                                </label>
                                <select
                                    name="user_id"
                                    value={form.user_id}
                                    onChange={handleChange}
                                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-neon-cyan/50 transition-all"
                                >
                                    <option value="">Select wallet...</option>
                                    {wallets.map((w) => (
                                        <option key={w.user_id} value={w.user_id}>
                                            {w.label || w.user_id} — {balanceText(balances[w.user_id]) || "loading..."}
                                        </option>
                                    ))}
                                </select>
                                {selectedBalance && (
                                    <div className="mt-2 text-xs text-gray-500">
                                        Available: <span className="text-white font-mono">{balanceText(selectedBalance)}</span>
                                    </div>
                                )}
                            </div>

                            {/* Recipient Address */}
                            <div>
                                <label className="block text-xs font-orbitron text-gray-400 mb-2 uppercase">
                                    Recipient Address
                                </label>
                                <input
                                    type="text"
                                    name="to_address"
                                    value={form.to_address}
                                    onChange={handleChange}
                                    placeholder="0x..."
                                    required
                                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white placeholder-gray-600 font-mono text-sm focus:outline-none focus:border-neon-cyan/50 transition-all"
                                />
                            </div>

                            {/* Amount */}
                            <div>
                                <label className="block text-xs font-orbitron text-gray-400 mb-2 uppercase">
                                    Amount (STRK)
                                </label>
                                <div className="relative">
                                    <input
                                        type="number"
                                        name="amount_strk"
                                        value={form.amount_strk}
                                        onChange={handleChange}
                                        placeholder="0.0"
                                        step="0.000001"
                                        min="0"
                                        required
                                        className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 pr-16 text-white placeholder-gray-600 focus:outline-none focus:border-neon-cyan/50 transition-all"
                                    />
                                    <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 text-sm font-mono">
                                        STRK
                                    </span>
                                </div>
                            </div>

                            {/* Pipeline Info */}
                            <div className="p-3 bg-black/20 rounded-lg border border-white/5">
                                <div className="text-xs text-gray-500 space-y-1">
                                    <div className="flex items-center gap-2">
                                        <span className="w-1.5 h-1.5 rounded-full bg-neon-cyan"></span>
                                        Sign with ML-DSA-44 quantum signature
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className="w-1.5 h-1.5 rounded-full bg-neon-purple"></span>
                                        Generate proof commitment (prover)
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className="w-1.5 h-1.5 rounded-full bg-neon-green"></span>
                                        Submit execute_with_proof to Starknet
                                    </div>
                                </div>
                            </div>

                            <Button
                                type="submit"
                                disabled={sending}
                                variant="primary"
                                className="w-full justify-center"
                            >
                                {sending ? (
                                    <span className="flex items-center gap-2">
                                        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                                        Signing & Submitting...
                                    </span>
                                ) : (
                                    "Send STRK"
                                )}
                            </Button>
                        </form>
                    </Card>

                    {/* Result Panel */}
                    <div className="space-y-6">
                        {/* Success Result */}
                        {result && result.status !== "proof_failed" && result.status !== "submission_failed" && (
                            <Card variant="default" className="border-l-4 border-l-neon-green">
                                <h3 className="text-neon-green font-orbitron font-bold mb-4 flex items-center gap-2">
                                    <span className="w-2 h-2 bg-neon-green rounded-full animate-pulse"></span>
                                    TRANSFER SUBMITTED
                                </h3>

                                <div className="space-y-3 text-sm">
                                    <div className="p-3 bg-black/20 rounded-lg">
                                        <span className="text-gray-500 block text-xs mb-1">TX ID</span>
                                        <span className="text-white font-mono text-xs">{result.tx_id}</span>
                                    </div>

                                    <div className="grid grid-cols-2 gap-3">
                                        <div className="p-3 bg-black/20 rounded-lg">
                                            <span className="text-gray-500 block text-xs mb-1">AMOUNT</span>
                                            <span className="text-white font-mono">{result.amount_strk} STRK</span>
                                        </div>
                                        <div className="p-3 bg-black/20 rounded-lg">
                                            <span className="text-gray-500 block text-xs mb-1">PROOF</span>
                                            <span className="text-neon-green font-mono">
                                                {result.proof_valid ? "VALID" : "INVALID"}
                                            </span>
                                        </div>
                                    </div>

                                    <div className="p-3 bg-black/20 rounded-lg">
                                        <span className="text-gray-500 block text-xs mb-1">PROVER BACKEND</span>
                                        <span className="text-neon-cyan font-mono text-xs">
                                            {result.prover_backend || "unknown"}
                                        </span>
                                    </div>

                                    {result.starknet_tx_hash && (
                                        <div className="p-3 bg-black/20 rounded-lg">
                                            <span className="text-gray-500 block text-xs mb-1">STARKNET TX</span>
                                            <a
                                                href={result.explorer_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="text-cyan-400 font-mono text-xs break-all hover:underline"
                                            >
                                                {result.starknet_tx_hash}
                                            </a>
                                        </div>
                                    )}

                                    <div className="p-3 bg-black/20 rounded-lg">
                                        <span className="text-gray-500 block text-xs mb-1">TO</span>
                                        <span className="text-gray-300 font-mono text-xs break-all">
                                            {result.to_address}
                                        </span>
                                    </div>

                                    {/* Live TX Status */}
                                    {txStatus && (
                                        <div className={`p-3 rounded-lg border ${txStatus.status === 'confirmed'
                                            ? 'bg-green-900/20 border-green-500/20'
                                            : txStatus.status === 'rejected' || txStatus.status === 'failed'
                                                ? 'bg-red-900/20 border-red-500/20'
                                                : 'bg-blue-900/20 border-blue-500/20'
                                            }`}>
                                            <span className="text-gray-500 block text-xs mb-1">ON-CHAIN STATUS</span>
                                            <span className={`font-mono text-sm ${txStatus.status === 'confirmed' ? 'text-green-400' :
                                                txStatus.status === 'rejected' || txStatus.status === 'failed' ? 'text-red-400' :
                                                    'text-blue-400'
                                                }`}>
                                                {txStatus.status.toUpperCase()}
                                            </span>
                                        </div>
                                    )}

                                    {polling && (
                                        <div className="p-3 rounded-lg border bg-blue-900/20 border-blue-500/20">
                                            <span className="text-blue-300 text-xs">Polling Starknet confirmation...</span>
                                        </div>
                                    )}

                                    {pollTimedOut && result?.tx_id && (
                                        <div className="p-3 rounded-lg border bg-yellow-900/20 border-yellow-500/20">
                                            <span className="text-yellow-300 text-xs block mb-2">
                                                Confirmation is taking longer than expected.
                                            </span>
                                            <button
                                                type="button"
                                                onClick={() => pollTxStatus(result.tx_id, { maxAttempts: 20, intervalMs: 3000 })}
                                                className="text-xs px-3 py-1 rounded border border-yellow-400/40 text-yellow-200 hover:bg-yellow-400/10"
                                            >
                                                Retry Status Check
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </Card>
                        )}

                        {/* Error States */}
                        {result && (result.status === "proof_failed" || result.status === "submission_failed") && (
                            <Card className="border-l-4 border-l-red-500 bg-red-500/5">
                                <h3 className="text-red-400 font-orbitron font-bold mb-2">
                                    {result.status === "proof_failed" ? "PROOF FAILED" : "SUBMISSION FAILED"}
                                </h3>
                                <p className="text-red-300 text-sm">{result.error}</p>
                            </Card>
                        )}

                        {error && (
                            <Card className="border-l-4 border-l-red-500 bg-red-500/5">
                                <p className="text-red-400 flex items-center gap-2">
                                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                    </svg>
                                    {error}
                                </p>
                            </Card>
                        )}

                        {/* Transfer Info */}
                        {!result && !error && (
                            <Card variant="default" title="How It Works">
                                <div className="space-y-4 text-sm text-gray-400">
                                    <div className="flex items-start gap-3">
                                        <span className="w-6 h-6 rounded-full bg-cyan-500/20 text-cyan-400 flex items-center justify-center text-xs shrink-0 mt-0.5">1</span>
                                        <div>
                                            <p className="text-gray-300">Quantum Signature</p>
                                            <p className="text-xs">Your transaction is signed with ML-DSA-44 (2,420 byte quantum-resistant signature)</p>
                                        </div>
                                    </div>
                                    <div className="flex items-start gap-3">
                                        <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-400 flex items-center justify-center text-xs shrink-0 mt-0.5">2</span>
                                        <div>
                                            <p className="text-gray-300">Proof Generation</p>
                                            <p className="text-xs">The prover verifies the signature and generates a 32-byte proof commitment</p>
                                        </div>
                                    </div>
                                    <div className="flex items-start gap-3">
                                        <span className="w-6 h-6 rounded-full bg-green-500/20 text-green-400 flex items-center justify-center text-xs shrink-0 mt-0.5">3</span>
                                        <div>
                                            <p className="text-gray-300">On-Chain Execution</p>
                                            <p className="text-xs">execute_with_proof() is called on your QuantumGuard contract on Starknet Sepolia</p>
                                        </div>
                                    </div>
                                </div>
                            </Card>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
