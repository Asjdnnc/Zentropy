import { useState, useEffect, useCallback } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { listWallets, getWalletBalance, getWalletInfo } from "../api/client";

export default function ReceiveTokens() {
    const [searchParams] = useSearchParams();
    const initialWallet = searchParams.get("wallet") || "";

    const [wallets, setWallets] = useState([]);
    const [selected, setSelected] = useState(initialWallet);
    const [balances, setBalances] = useState({});
    const [copied, setCopied] = useState(false);

    const fetchWallets = useCallback(async () => {
        try {
            const res = await listWallets();
            const users = res.data.users || res.data.wallets || [];
            const enriched = await Promise.all(
                users.map(async (u) => {
                    const userId = u.user_id || u.label;
                    if (!userId) return null;
                    try {
                        const walletRes = await getWalletInfo(userId);
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

            if (!selected && w.length > 0) {
                setSelected(w[0].user_id);
            }

            const balanceResults = await Promise.all(
                w.map((wallet) =>
                    getWalletBalance(wallet.user_id)
                        .then((r) => ({ user_id: wallet.user_id, data: r.data }))
                        .catch(() => null)
                )
            );
            const b = {};
            balanceResults.forEach((r) => {
                if (r) b[r.user_id] = r.data;
            });
            setBalances(b);
        } catch {
            // noop
        }
    }, [selected]);

    useEffect(() => {
        const timer = setTimeout(() => {
            fetchWallets();
        }, 0);
        return () => clearTimeout(timer);
    }, [fetchWallets]);

    const wallet = wallets.find((w) => w.user_id === selected);
    const balance = balances[selected];
    const balanceText = balance?.balance_display || balance?.balance_strk || "0.000";

    async function copyAddress() {
        if (!wallet?.contract_address) return;
        try {
            await navigator.clipboard.writeText(wallet.contract_address);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            const ta = document.createElement("textarea");
            ta.value = wallet.contract_address;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand("copy");
            document.body.removeChild(ta);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    }

    return (
        <div className="space-y-8 animate-fade-in text-white font-sans max-w-7xl mx-auto w-full">
            <div className="mb-8 pl-1">
                <h1 className="text-2xl font-bold tracking-tight mb-2">Receive STRK</h1>
                <p className="text-gray-400 text-[14px]">
                    Share your contract address to receive tokens on Starknet Sepolia
                </p>
            </div>

            {wallets.length === 0 ? (
                <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-12 text-center shadow-xl w-full">
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
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-10 items-start w-full">
                    {/* Left Column: Wallet Selector & Info */}
                    <div className="space-y-8 w-full">
                        {/* Wallet Selector */}
                        <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-8 md:p-10 shadow-xl w-full">
                            <label className="block text-[13px] font-medium text-gray-400 mb-3 ml-1">
                                Destination Wallet
                            </label>
                            <select
                                value={selected}
                                onChange={(e) => {
                                    setSelected(e.target.value);
                                    setCopied(false);
                                }}
                                className="w-full bg-[#111] border border-[#222] focus:border-[#444] rounded-xl px-4 py-3.5 text-[14px] text-white outline-none transition-all appearance-none cursor-pointer"
                            >
                                {wallets.map((w) => {
                                    const b = balances[w.user_id];
                                    const balText = b?.balance_display || b?.balance_strk || "0.0";
                                    return (
                                        <option key={w.user_id} value={w.user_id}>
                                            {w.wallet_name || w.username || w.label || w.user_id} ({balText} STRK)
                                        </option>
                                    );
                                })}
                            </select>
                        </div>

                        {/* Wallet Info */}
                        {wallet && (
                            <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-8 md:p-10 shadow-xl w-full">
                                <h3 className="text-[14px] font-medium text-white mb-6 border-b border-[#1a1a1a] pb-4">Wallet Configuration</h3>
                                <div className="space-y-4 text-[13px]">
                                    <div className="flex justify-between items-center bg-[#111] px-4 py-3 rounded-xl border border-[#222]">
                                        <span className="text-gray-500 font-medium">Label</span>
                                        <span className="text-white font-mono">{wallet.label || wallet.user_id}</span>
                                    </div>
                                    <div className="flex justify-between items-center bg-[#111] px-4 py-3 rounded-xl border border-[#222]">
                                        <span className="text-gray-500 font-medium">Algorithm</span>
                                        <span className="text-white font-mono bg-[#1a1a1a] px-2 py-0.5 rounded border border-[#333]">ML-DSA-44</span>
                                    </div>
                                    <div className="flex justify-between items-center bg-[#111] px-4 py-3 rounded-xl border border-[#222]">
                                        <span className="text-gray-500 font-medium">Network</span>
                                        <span className="text-white font-mono">Starknet Sepolia</span>
                                    </div>
                                    <div className="flex justify-between items-center bg-[#111] px-4 py-3 rounded-xl border border-[#222]">
                                        <span className="text-gray-500 font-medium">Status</span>
                                        <span className="text-green-400 font-mono font-medium flex items-center gap-2">
                                            <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></span>
                                            Deployed
                                        </span>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Right Column: QR/Address Display & Warning */}
                    <div className="space-y-8 w-full">
                        {/* Address Display */}
                        {wallet && (
                            <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-8 md:p-10 shadow-2xl relative overflow-hidden text-center w-full">
                                <div className="absolute top-0 left-0 w-full h-[2px] bg-white/10"></div>
                                
                                <div className="space-y-8 pt-2">
                                    {/* Large Address Display */}
                                    <div>
                                        <p className="text-[11px] font-medium tracking-wider uppercase text-gray-500 mb-4">
                                            Your Contract Address
                                        </p>
                                        <div className="p-6 bg-[#111] border border-[#222] rounded-[16px] w-full">
                                            <p className="text-white font-mono text-[15px] break-all leading-relaxed select-all">
                                                {wallet.contract_address}
                                            </p>
                                        </div>
                                    </div>

                                    {/* Copy Button */}
                                    <button
                                        onClick={copyAddress}
                                        className={`w-full py-4 rounded-[16px] text-[15px] font-semibold transition-all flex items-center justify-center gap-2 shadow-lg ${copied
                                            ? "bg-green-500/10 border border-green-500/30 text-green-400"
                                            : "bg-white text-black hover:bg-gray-200 border border-transparent"
                                            }`}
                                    >
                                        {copied ? (
                                            <>
                                                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                                </svg>
                                                Copied to Clipboard!
                                            </>
                                        ) : (
                                            <>
                                                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                                </svg>
                                                Copy Address
                                            </>
                                        )}
                                    </button>

                                    <div>
                                        <a
                                            href={`https://sepolia.voyager.online/contract/${wallet.contract_address}`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="inline-flex items-center justify-center w-full gap-2 text-blue-400 hover:text-white text-[13px] font-medium transition-colors"
                                        >
                                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                            </svg>
                                            View on Voyager Block Explorer
                                        </a>
                                    </div>

                                    {/* Balance */}
                                    {balance && (
                                        <div className="pt-6 border-t border-[#1a1a1a]">
                                            <p className="text-[11px] font-medium tracking-wider uppercase text-gray-500 mb-2">Current Balance</p>
                                            <div className="flex items-center justify-center gap-2">
                                                <p className="text-3xl font-mono text-white font-bold tracking-tight">{balanceText}</p>
                                                <span className="text-gray-400 text-lg font-medium">STRK</span>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* Warning */}
                        <div className="p-5 bg-yellow-500/5 border border-yellow-500/20 rounded-[16px] flex items-start gap-4 shadow-xl w-full">
                            <div className="w-8 h-8 rounded-full bg-yellow-500/10 flex items-center justify-center shrink-0 border border-yellow-500/20">
                                <svg className="w-4 h-4 text-yellow-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                                </svg>
                            </div>
                            <div>
                                <p className="text-yellow-500 text-[14px] font-semibold mb-1">Starknet Sepolia Testnet Only</p>
                                <p className="text-gray-400 text-[13px] leading-relaxed">
                                    Only send STRK tokens natively located on the Starknet Sepolia testnet to this contract address.
                                    Sending tokens from Mainnet or other L1 networks will result in permanent unrecoverable loss.
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
