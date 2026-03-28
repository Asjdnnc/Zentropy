import { useState } from 'react';
import { Link } from 'react-router-dom';
import { deployWalletContract } from '../api/client';

export default function WalletCard({ wallet, balance, onSelect, showActions = true, className = "" }) {
    const [copied, setCopied] = useState(null);
    const [deploying, setDeploying] = useState(false);
    const [deployError, setDeployError] = useState(null);

    const isDeployed = wallet.deployment_status === 'deployed' && wallet.contract_address;
    const isFailed = wallet.deployment_status === 'failed';
    const identityHash = wallet.pubkey_hash || wallet.public_key_hash || '';
    const senderModel = wallet.sender_model || 'relayer';
    const submitterAddress = wallet.submitter_address || '';

    const statusColor = isDeployed
        ? 'text-green-400 bg-green-500/10 border border-green-500/20'
        : isFailed
            ? 'text-yellow-500 bg-yellow-500/10 border border-yellow-500/20'
            : 'text-blue-400 bg-blue-500/10 border border-blue-500/20';

    const statusText = isDeployed ? 'DEPLOYED' : isFailed ? 'FAILED' : 'PENDING';

    async function copyToClipboard(text, field) {
        try {
            await navigator.clipboard.writeText(text);
            setCopied(field);
            setTimeout(() => setCopied(null), 2000);
        } catch {
            // fallback
        }
    }

    async function handleRetryDeploy(e) {
        e.stopPropagation();
        setDeploying(true);
        setDeployError(null);
        try {
            const response = await deployWalletContract(wallet.user_id || wallet.label);
            window.location.reload();
        } catch (err) {
            setDeployError(err.readableMessage || err.response?.data?.detail || 'Deploy failed');
        } finally {
            setDeploying(false);
        }
    }

    return (
        <div
            onClick={() => onSelect?.(wallet)}
            className={`bg-[#0a0a0a] border border-[#1a1a1a] rounded-[20px] p-6 hover:border-blue-500/30 transition-all cursor-pointer group relative overflow-hidden ${className}`}
        >
            {/* Top Indicator Line */}
            {isDeployed && (
                <div className="absolute top-0 left-0 w-full h-[2px] bg-green-500/20"></div>
            )}

            {/* Header */}
            <div className="flex items-start justify-between mb-5">
                <h3 className="text-white font-semibold text-[16px] group-hover:text-blue-400 transition-colors tracking-tight">
                    {wallet.wallet_name || wallet.username || wallet.label || wallet.user_id || 'default'}
                </h3>
                <div className="flex items-center gap-2">
                    <span className={`text-[11px] font-medium px-2 py-0.5 rounded-md ${statusColor}`}>
                        {statusText}
                    </span>
                    <span className="text-[11px] font-medium text-gray-400 bg-[#111] border border-[#222] px-2 py-0.5 rounded-md">
                        {wallet.algorithm}
                    </span>
                </div>
            </div>

            <div className="space-y-4">
                {/* Balance Display */}
                {isDeployed && (
                    <div className="p-4 bg-[#111] border border-[#222] rounded-xl flex items-center justify-between">
                        <div>
                            <span className="text-gray-500 text-[11px] block mb-0.5 font-medium uppercase tracking-wider">Balance</span>
                            <div className="flex items-baseline gap-1.5">
                                <span className="text-[20px] font-bold text-white font-mono tracking-tight">
                                    {balance?.balance_strk || '0.000'}
                                </span>
                                <span className="text-gray-400 text-[13px] font-medium">STRK</span>
                            </div>
                        </div>
                        {balance?.stale && (
                            <span className="text-yellow-500 text-[11px] font-medium bg-yellow-500/10 px-2 py-0.5 rounded-md border border-yellow-500/20">cached</span>
                        )}
                    </div>
                )}

                {/* Contract Address */}
                {isDeployed && (
                    <div>
                        <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider mb-1 block">Contract Address</span>
                        <div className="flex items-center gap-2">
                            <p className="text-green-400 font-mono text-[13px] break-all flex-1">
                                {wallet.contract_address.slice(0, 10)}...{wallet.contract_address.slice(-8)}
                            </p>
                            <button
                                onClick={(e) => { e.stopPropagation(); copyToClipboard(wallet.contract_address, 'contract'); }}
                                className="text-gray-500 hover:text-white transition-colors shrink-0"
                                title="Copy contract address"
                            >
                                {copied === 'contract' ? (
                                    <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                                ) : (
                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                                )}
                            </button>
                            <a
                                href={`https://sepolia.voyager.online/contract/${wallet.contract_address}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="text-gray-500 hover:text-white transition-colors shrink-0"
                                title="View on Voyager"
                            >
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                            </a>
                        </div>
                    </div>
                )}

                {/* Identity Hash */}
                <div>
                    <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider mb-1 block">Identity Hash</span>
                    <div className="flex items-center gap-2">
                        <p className="text-gray-300 font-mono text-[13px] break-all flex-1">
                            {identityHash ? identityHash.slice(0, 24) + '...' : 'N/A'}
                        </p>
                        <button
                            onClick={(e) => { e.stopPropagation(); if (identityHash) copyToClipboard(identityHash, 'hash'); }}
                            className="text-gray-500 hover:text-white transition-colors shrink-0"
                            title="Copy identity hash"
                        >
                            {copied === 'hash' ? (
                                <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                            ) : (
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                            )}
                        </button>
                    </div>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider mb-1 block">Sender Mode</span>
                        <p className="text-gray-300 text-[13px] font-medium">{senderModel}</p>
                    </div>
                    {wallet.created_at && (
                        <div>
                            <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider mb-1 block">Created</span>
                            <p className="text-gray-300 text-[13px] font-medium">{new Date(wallet.created_at * 1000).toLocaleDateString()}</p>
                        </div>
                    )}
                </div>

                {/* Failed deploy — retry button */}
                {isFailed && (
                    <div className="pt-3">
                        <button
                            onClick={handleRetryDeploy}
                            disabled={deploying}
                            className="w-full px-4 py-2.5 bg-yellow-500/10 border border-yellow-500/20 text-yellow-500 rounded-xl text-[13px] font-medium hover:bg-yellow-500/20 transition-colors disabled:opacity-50"
                        >
                            {deploying ? 'Deploying...' : 'Retry Contract Deployment'}
                        </button>
                        {deployError && (
                            <p className="text-red-400 text-[12px] mt-2">{deployError}</p>
                        )}
                    </div>
                )}

                {/* Action Buttons for deployed wallets */}
                {isDeployed && showActions && (
                    <div className="flex gap-3 pt-3">
                        <Link
                            to={`/send?wallet=${wallet.user_id || wallet.label}`}
                            onClick={(e) => e.stopPropagation()}
                            className="flex-1 py-2.5 bg-white text-black font-semibold rounded-xl text-[13px] text-center hover:bg-gray-200 transition-colors"
                        >
                            Send
                        </Link>
                        <Link
                            to={`/receive?wallet=${wallet.user_id || wallet.label}`}
                            onClick={(e) => e.stopPropagation()}
                            className="flex-1 py-2.5 bg-transparent border border-[#333] text-white font-semibold rounded-xl text-[13px] text-center hover:bg-[#111] transition-colors"
                        >
                            Receive
                        </Link>
                    </div>
                )}
            </div>
        </div>
    );
}
