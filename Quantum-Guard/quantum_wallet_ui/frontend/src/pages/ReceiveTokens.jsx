import { useState, useEffect } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { listWallets, getWalletBalance } from "../api/client";
import Card from "../components/Card";

export default function ReceiveTokens() {
    const [searchParams] = useSearchParams();
    const initialWallet = searchParams.get("wallet") || "";

    const [wallets, setWallets] = useState([]);
    const [selected, setSelected] = useState(initialWallet);
    const [balances, setBalances] = useState({});
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        fetchWallets();
    }, []);

    async function fetchWallets() {
        try {
            const res = await listWallets();
            const w = (res.data.wallets || []).filter(
                (wallet) => wallet.contract_address && wallet.deployment_status === "deployed"
            );
            setWallets(w);

            if (!selected && w.length > 0) {
                setSelected(w[0].label);
            }

            const balanceResults = await Promise.all(
                w.map((wallet) =>
                    getWalletBalance(wallet.label)
                        .then((r) => ({ label: wallet.label, data: r.data }))
                        .catch(() => null)
                )
            );
            const b = {};
            balanceResults.forEach((r) => {
                if (r) b[r.label] = r.data;
            });
            setBalances(b);
        } catch {
            // noop
        }
    }

    const wallet = wallets.find((w) => w.label === selected);
    const balance = balances[selected];

    async function copyAddress() {
        if (!wallet?.contract_address) return;
        try {
            await navigator.clipboard.writeText(wallet.contract_address);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // fallback
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
        <div className="space-y-8 animate-fade-in">
            <div>
                <h1 className="text-3xl font-bold font-orbitron text-white">
                    Receive STRK
                </h1>
                <p className="text-gray-400 mt-1">
                    Share your contract address to receive tokens on Starknet Sepolia
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
                <div className="max-w-xl mx-auto space-y-6">
                    {/* Wallet Selector */}
                    <Card variant="default">
                        <label className="block text-xs font-orbitron text-gray-400 mb-2 uppercase">
                            Select Wallet
                        </label>
                        <select
                            value={selected}
                            onChange={(e) => {
                                setSelected(e.target.value);
                                setCopied(false);
                            }}
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-neon-cyan/50 transition-all"
                        >
                            {wallets.map((w) => (
                                <option key={w.label} value={w.label}>
                                    {w.label}
                                </option>
                            ))}
                        </select>
                    </Card>

                    {/* Address Display */}
                    {wallet && (
                        <Card variant="neon" className="text-center">
                            <div className="space-y-6">
                                {/* Large Address Display */}
                                <div>
                                    <p className="text-xs text-gray-500 font-orbitron mb-3 uppercase">
                                        Your Contract Address
                                    </p>
                                    <div className="p-4 bg-black/30 border border-white/10 rounded-xl">
                                        <p className="text-white font-mono text-sm break-all leading-relaxed select-all">
                                            {wallet.contract_address}
                                        </p>
                                    </div>
                                </div>

                                {/* Copy Button */}
                                <button
                                    onClick={copyAddress}
                                    className={`w-full py-3 rounded-lg font-orbitron text-sm transition-all flex items-center justify-center gap-2 ${copied
                                            ? "bg-neon-green/20 border border-neon-green/50 text-neon-green"
                                            : "bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan hover:bg-neon-cyan/20"
                                        }`}
                                >
                                    {copied ? (
                                        <>
                                            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                            </svg>
                                            Copied!
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

                                {/* Explorer Link */}
                                <a
                                    href={`https://sepolia.starkscan.co/contract/${wallet.contract_address}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex items-center gap-2 text-cyan-400 hover:text-cyan-300 text-sm transition-colors"
                                >
                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                    </svg>
                                    View on Starkscan
                                </a>

                                {/* Balance */}
                                {balance && (
                                    <div className="pt-4 border-t border-white/10">
                                        <p className="text-xs text-gray-500 mb-1">CURRENT BALANCE</p>
                                        <p className="text-2xl font-mono text-white">{balance.balance_display}</p>
                                    </div>
                                )}
                            </div>
                        </Card>
                    )}

                    {/* Warning */}
                    <div className="p-4 bg-yellow-500/5 border border-yellow-500/20 rounded-lg flex items-start gap-3">
                        <svg className="w-5 h-5 text-yellow-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                        </svg>
                        <div>
                            <p className="text-yellow-400 text-sm font-medium">Starknet Sepolia Only</p>
                            <p className="text-yellow-500/70 text-xs mt-1">
                                Only send STRK tokens on the Starknet Sepolia testnet to this address.
                                Sending tokens from other networks will result in permanent loss.
                            </p>
                        </div>
                    </div>

                    {/* Wallet Info */}
                    {wallet && (
                        <Card variant="default" title="Wallet Details">
                            <div className="space-y-3 text-sm">
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Label</span>
                                    <span className="text-white font-mono">{wallet.label}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Algorithm</span>
                                    <span className="text-white font-mono">ML-DSA-44</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Network</span>
                                    <span className="text-white font-mono">Starknet Sepolia</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-gray-500">Status</span>
                                    <span className="text-neon-green font-mono">Deployed</span>
                                </div>
                            </div>
                        </Card>
                    )}
                </div>
            )}
        </div>
    );
}
