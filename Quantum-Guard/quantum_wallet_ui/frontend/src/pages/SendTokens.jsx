import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { listWallets, getWalletBalance, executeTransfer, getTransferStatus, getWalletInfo, setActiveUserId } from "../api/client";
import { useWallet } from "../context/WalletContext";

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

    const balanceText = (b) => b?.balance_display || b?.balance_strk || "0.000";

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
            if (isAbortError(err)) return;
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

            await refreshAll();
            await fetchWallets();

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
        <div className="space-y-8 animate-fade-in text-white font-sans max-w-7xl mx-auto w-full">
            <div className="mb-8 pl-1">
                <h1 className="text-2xl font-bold tracking-tight mb-2">Send STRK</h1>
                <p className="text-gray-400 text-[14px]">
                    Transfer tokens using quantum-resistant signatures (ML-DSA-44)
                </p>
            </div>

            {wallets.length === 0 ? (
                <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-12 text-center shadow-xl">
                    <p className="text-gray-400 mb-6 text-[14px]">
                        No deployed wallets found. Create a wallet first.
                    </p>
                    <Link
                        to="/wallet"
                        className="inline-flex py-3 px-6 bg-white text-black font-semibold rounded-xl text-[14px] hover:bg-gray-200 transition-colors"
                    >
                        Initialize Wallet
                    </Link>
                </div>
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
                    {/* Transfer Form */}
                    <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-8 md:p-10 shadow-2xl h-fit">
                        <h2 className="text-lg font-semibold tracking-tight text-white mb-8 border-b border-[#1a1a1a] pb-5">Transfer Details</h2>
                        
                        <form onSubmit={handleSubmit} className="space-y-6">
                            {/* Wallet Selector */}
                            <div className="space-y-2">
                                <label className="block text-[13px] font-medium text-gray-400 ml-1">
                                    From Wallet
                                </label>
                                <select
                                    name="user_id"
                                    value={form.user_id}
                                    onChange={handleChange}
                                    className="w-full bg-[#111] border border-[#222] focus:border-[#444] rounded-xl px-4 py-3.5 text-[14px] text-white outline-none transition-all appearance-none cursor-pointer"
                                >
                                    <option value="" className="text-gray-500">Select wallet...</option>
                                    {wallets.map((w) => (
                                        <option key={w.user_id} value={w.user_id}>
                                            {w.wallet_name || w.username || w.label || w.user_id} ({balanceText(balances[w.user_id])} STRK)
                                        </option>
                                    ))}
                                </select>
                                {selectedBalance && (
                                    <div className="flex justify-between items-center px-1 pt-1 opacity-80">
                                        <span className="text-[11px] text-gray-500 uppercase tracking-wider font-medium">Available</span>
                                        <span className="text-[12px] text-white font-mono">{balanceText(selectedBalance)} STRK</span>
                                    </div>
                                )}
                            </div>

                            {/* Recipient Address */}
                            <div className="space-y-2">
                                <label className="block text-[13px] font-medium text-gray-400 ml-1">
                                    Recipient Address
                                </label>
                                <input
                                    type="text"
                                    name="to_address"
                                    value={form.to_address}
                                    onChange={handleChange}
                                    placeholder="0x..."
                                    required
                                    className="w-full bg-[#111] border border-[#222] focus:border-[#444] rounded-xl px-4 py-3.5 text-[14px] text-white placeholder-gray-600 font-mono outline-none transition-all"
                                />
                            </div>

                            {/* Amount */}
                            <div className="space-y-2">
                                <label className="block text-[13px] font-medium text-gray-400 ml-1">
                                    Amount (STRK)
                                </label>
                                <div className="relative">
                                    <input
                                        type="number"
                                        name="amount_strk"
                                        value={form.amount_strk}
                                        onChange={handleChange}
                                        placeholder="0.00"
                                        step="0.000001"
                                        min="0"
                                        required
                                        className="w-full bg-[#111] border border-[#222] focus:border-[#444] rounded-xl px-4 py-3.5 pr-16 text-[14px] text-white placeholder-gray-600 font-mono outline-none transition-all"
                                    />
                                    <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 text-[13px] font-medium bg-[#1a1a1a] px-2 py-1 rounded-md">
                                        STRK
                                    </span>
                                </div>
                            </div>

                            {/* Pipeline Info */}
                            <div className="p-4 bg-blue-900/5 border border-blue-500/10 rounded-xl mt-8">
                                <div className="text-[12px] text-gray-400 space-y-3">
                                    <div className="flex items-center gap-3">
                                        <div className="w-5 h-5 rounded-full bg-blue-500/10 flex items-center justify-center shrink-0">
                                            <span className="w-1.5 h-1.5 rounded-full bg-blue-400"></span>
                                        </div>
                                        <span>Sign with ML-DSA-44 quantum signature</span>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <div className="w-5 h-5 rounded-full bg-purple-500/10 flex items-center justify-center shrink-0">
                                            <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
                                        </div>
                                        <span>Generate proof commitment (prover)</span>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <div className="w-5 h-5 rounded-full bg-green-500/10 flex items-center justify-center shrink-0">
                                            <span className="w-1.5 h-1.5 rounded-full bg-green-400"></span>
                                        </div>
                                        <span>Submit execute_with_proof to Starknet</span>
                                    </div>
                                </div>
                            </div>

                            <div className="pt-4">
                                <button
                                    type="submit"
                                    disabled={sending}
                                    className="w-full flex items-center justify-center py-4 rounded-[16px] bg-white text-black text-[15px] font-semibold hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-[0_0_20px_rgba(255,255,255,0.1)]"
                                >
                                    {sending ? (
                                        <span className="flex items-center gap-2">
                                            <svg className="animate-spin h-4 w-4 text-black" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                                            Signing & Submitting...
                                        </span>
                                    ) : (
                                        "Authenticate & Send STRK"
                                    )}
                                </button>
                            </div>
                        </form>
                    </div>

                    {/* Result Panel */}
                    <div className="space-y-6">
                        {/* Success Result */}
                        {result && result.status !== "proof_failed" && result.status !== "submission_failed" && (
                            <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] overflow-hidden shadow-2xl relative">
                                <div className="absolute top-0 left-0 w-full h-1 bg-green-500"></div>
                                <div className="p-8">
                                    <h3 className="text-green-400 font-semibold mb-6 flex items-center gap-3 text-[14px] tracking-wide uppercase">
                                        <div className="w-2.5 h-2.5 bg-green-500 rounded-full animate-pulse shadow-[0_0_10px_rgba(34,197,94,0.5)]"></div>
                                        Transfer Submitted
                                    </h3>

                                    <div className="space-y-4 text-sm">
                                        <div className="p-4 bg-[#111] border border-[#222] rounded-xl flex justify-between items-center">
                                            <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider">Amount</span>
                                            <span className="text-white font-mono text-[16px] font-bold">{result.amount_strk} STRK</span>
                                        </div>

                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="p-4 bg-[#111] border border-[#222] rounded-xl">
                                                <span className="text-gray-500 block text-[11px] font-medium uppercase tracking-wider mb-1">Status</span>
                                                <span className="text-white font-mono text-[13px]">Submitted</span>
                                            </div>
                                            <div className="p-4 bg-[#111] border border-[#222] rounded-xl">
                                                <span className="text-gray-500 block text-[11px] font-medium uppercase tracking-wider mb-1">ZK Proof</span>
                                                <span className="text-green-400 font-mono text-[13px] font-medium">
                                                    {result.proof_valid ? "VALID" : "INVALID"}
                                                </span>
                                            </div>
                                        </div>

                                        <div className="p-4 bg-[#111] border border-[#222] rounded-xl">
                                            <span className="text-gray-500 block text-[11px] font-medium uppercase tracking-wider mb-1">TX ID</span>
                                            <span className="text-white font-mono text-[13px] break-all">{result.tx_id}</span>
                                        </div>

                                        <div className="p-4 bg-[#111] border border-[#222] rounded-xl">
                                            <span className="text-gray-500 block text-[11px] font-medium uppercase tracking-wider mb-1">Prover Backend</span>
                                            <span className="text-blue-400 font-mono text-[13px]">
                                                {result.prover_backend || "unknown"}
                                            </span>
                                        </div>

                                        {result.starknet_tx_hash && (
                                            <div className="p-4 bg-[#111] border border-[#222] rounded-xl">
                                                <span className="text-gray-500 block text-[11px] font-medium uppercase tracking-wider mb-1">Starknet TX</span>
                                                <a
                                                    href={result.explorer_url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="text-white font-mono text-[13px] break-all hover:text-blue-400 transition-colors flex items-center justify-between"
                                                >
                                                    {result.starknet_tx_hash.slice(0, 14)}...{result.starknet_tx_hash.slice(-14)}
                                                    <svg className="w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                                </a>
                                            </div>
                                        )}

                                        <div className="p-4 bg-[#111] border border-[#222] rounded-xl">
                                            <span className="text-gray-500 block text-[11px] font-medium uppercase tracking-wider mb-1">To</span>
                                            <span className="text-gray-300 font-mono text-[13px] break-all">
                                                {result.to_address}
                                            </span>
                                        </div>

                                        {/* Live TX Status */}
                                        {txStatus && (
                                            <div className={`p-4 rounded-xl border ${txStatus.status === 'confirmed'
                                                ? 'bg-green-500/10 border-green-500/20'
                                                : txStatus.status === 'rejected' || txStatus.status === 'failed'
                                                    ? 'bg-red-500/10 border-red-500/20'
                                                    : 'bg-blue-500/10 border-blue-500/20'
                                                }`}>
                                                <span className="text-gray-500 block text-[11px] font-medium uppercase tracking-wider mb-1">On-chain Status</span>
                                                <span className={`font-mono text-[14px] font-semibold ${txStatus.status === 'confirmed' ? 'text-green-400' :
                                                    txStatus.status === 'rejected' || txStatus.status === 'failed' ? 'text-red-400' :
                                                        'text-blue-400'
                                                    }`}>
                                                    {txStatus.status.toUpperCase()}
                                                </span>
                                            </div>
                                        )}

                                        {polling && (
                                            <div className="p-4 rounded-xl border bg-blue-500/5 border-blue-500/20 flex items-center justify-center gap-3">
                                                <span className="w-4 h-4 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin"></span>
                                                <span className="text-blue-400 text-[13px] font-medium">Polling Starknet confirmation...</span>
                                            </div>
                                        )}

                                        {pollTimedOut && result?.tx_id && (
                                            <div className="p-4 rounded-xl border bg-yellow-500/10 border-yellow-500/20 text-center">
                                                <span className="text-yellow-500 text-[13px] block mb-3 font-medium">
                                                    Confirmation is taking longer than expected.
                                                </span>
                                                <button
                                                    type="button"
                                                    onClick={() => pollTxStatus(result.tx_id, { maxAttempts: 20, intervalMs: 3000 })}
                                                    className="text-[12px] px-4 py-2 font-medium bg-yellow-500/10 rounded-lg border border-yellow-500/20 text-yellow-500 hover:bg-yellow-500/20 transition-colors"
                                                >
                                                    Retry Status Check
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Error States */}
                        {result && (result.status === "proof_failed" || result.status === "submission_failed") && (
                            <div className="bg-red-500/5 border border-red-500/20 rounded-[24px] p-6 shadow-xl relative overflow-hidden">
                                <div className="absolute top-0 left-0 w-1 h-full bg-red-500"></div>
                                <h3 className="text-red-400 font-semibold mb-2 flex items-center gap-2 text-[14px] uppercase tracking-wide">
                                    <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                    {result.status === "proof_failed" ? "Proof Verification Failed" : "Submission Failed"}
                                </h3>
                                <p className="text-red-300 text-[13px]">{result.error}</p>
                            </div>
                        )}

                        {error && (
                            <div className="bg-red-500/5 border border-red-500/20 rounded-[16px] p-5 shadow-xl">
                                <p className="text-red-400 text-[13px] font-medium flex items-start gap-3">
                                    <svg className="w-5 h-5 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                    </svg>
                                    {error}
                                </p>
                            </div>
                        )}

                        {/* Transfer Info */}
                        {!result && !error && (
                            <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-8 md:p-10 shadow-xl">
                                <h2 className="text-lg font-semibold tracking-tight text-white mb-6">How It Works</h2>
                                <div className="space-y-6 text-[13px] text-gray-400">
                                    <div className="flex items-start gap-4">
                                        <span className="w-7 h-7 rounded-full bg-blue-500/10 text-blue-400 flex items-center justify-center text-[12px] font-semibold shrink-0 border border-blue-500/20 shadow-[0_0_10px_rgba(59,130,246,0.1)]">1</span>
                                        <div>
                                            <p className="text-gray-200 font-medium mb-1">Quantum Signature</p>
                                            <p className="text-gray-500 leading-relaxed">Your transaction is cryptographically signed locally using the ML-DSA-44 post-quantum algorithm, generating a massive 2,420-byte footprint.</p>
                                        </div>
                                    </div>
                                    <div className="flex items-start gap-4">
                                        <span className="w-7 h-7 rounded-full bg-purple-500/10 text-purple-400 flex items-center justify-center text-[12px] font-semibold shrink-0 border border-purple-500/20 shadow-[0_0_10px_rgba(168,85,247,0.1)]">2</span>
                                        <div>
                                            <p className="text-gray-200 font-medium mb-1">Co-Processor Proof Generation</p>
                                            <p className="text-gray-500 leading-relaxed">Our execution node verifies the robust signature and seamlessly rolls it up into a lightweight 32-byte cryptographic proof commitment.</p>
                                        </div>
                                    </div>
                                    <div className="flex items-start gap-4">
                                        <span className="w-7 h-7 rounded-full bg-green-500/10 text-green-400 flex items-center justify-center text-[12px] font-semibold shrink-0 border border-green-500/20 shadow-[0_0_10px_rgba(34,197,94,0.1)]">3</span>
                                        <div>
                                            <p className="text-gray-200 font-medium mb-1">On-Chain Finality</p>
                                            <p className="text-gray-500 leading-relaxed"><code className="text-gray-400 bg-[#111] px-1.5 py-0.5 rounded border border-[#222]">execute_with_proof()</code> is efficiently fired on your personalized QuantumGuard smart-contract deployed on Starknet.</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
