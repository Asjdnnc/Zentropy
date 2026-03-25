import { useState } from 'react';
import { Link } from 'react-router-dom';
import { deployWalletContract } from '../api/client';

export default function WalletCard({ wallet, balance, onSelect, showActions = true }) {
    const [copied, setCopied] = useState(null);
    const [deploying, setDeploying] = useState(false);
    const [deployError, setDeployError] = useState(null);

    const isDeployed = wallet.deployment_status === 'deployed' && wallet.contract_address;
    const isFailed = wallet.deployment_status === 'failed';
    const identityHash = wallet.pubkey_hash || wallet.public_key_hash || '';

    const statusColor = isDeployed
        ? 'text-green-400 bg-green-500/10 border-green-500/20'
        : isFailed
            ? 'text-red-400 bg-red-500/10 border-red-500/20'
            : 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20';

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
        console.log('[WalletCard] retry_deploy:start', {
            user_id: wallet.user_id || wallet.label,
            deployment_status: wallet.deployment_status,
            contract_address: wallet.contract_address,
        });
        try {
            const response = await deployWalletContract(wallet.user_id || wallet.label);
            console.log('[WalletCard] retry_deploy:queued', response?.data || null);
            window.location.reload();
        } catch (err) {
            console.error('[WalletCard] retry_deploy:error', {
                message: err?.message,
                readableMessage: err?.readableMessage,
                status: err?.response?.status,
                detail: err?.response?.data?.detail,
            });
            setDeployError(
                err.readableMessage ||
                err.response?.data?.detail ||
                'Deploy failed'
            );
        } finally {
            setDeploying(false);
        }
    }

    return (
        <div
            onClick={() => onSelect?.(wallet)}
            className="bg-gray-800/80 border border-gray-700 rounded-xl p-5 hover:border-indigo-500/50 transition-all cursor-pointer group relative overflow-hidden"
        >
            {/* Glow effect for deployed wallets */}
            {isDeployed && (
                <div className="absolute top-0 left-0 w-full h-0.5 bg-gradient-to-r from-green-500/0 via-green-500/50 to-green-500/0"></div>
            )}

            {/* Header */}
            <div className="flex items-start justify-between mb-3">
                <h3 className="text-white font-semibold text-lg group-hover:text-indigo-400 transition-colors">
                    {wallet.label || 'default'}
                </h3>
                <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-1 rounded border ${statusColor}`}>
                        {statusText}
                    </span>
                    <span className="text-xs text-gray-500 bg-gray-700/50 px-2 py-1 rounded">
                        {wallet.algorithm}
                    </span>
                </div>
            </div>

            <div className="space-y-3 text-sm">
                {/* Balance Display */}
                {isDeployed && (
                    <div className="p-3 bg-black/30 rounded-lg border border-white/5">
                        <span className="text-gray-500 text-xs block mb-1">BALANCE</span>
                        <div className="flex items-baseline gap-2">
                            <span className="text-2xl font-bold text-white font-mono">
                                {balance?.balance_strk || '0.000000'}
                            </span>
                            <span className="text-gray-400 text-sm">STRK</span>
                        </div>
                        {balance?.stale && (
                            <span className="text-yellow-500 text-xs">cached</span>
                        )}
                    </div>
                )}

                {/* Contract Address */}
                {isDeployed && (
                    <div>
                        <span className="text-gray-500 text-xs">Contract Address</span>
                        <div className="flex items-center gap-2 mt-0.5">
                            <p className="text-cyan-400 font-mono text-xs break-all flex-1">
                                {wallet.contract_address.slice(0, 10)}...{wallet.contract_address.slice(-8)}
                            </p>
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    copyToClipboard(wallet.contract_address, 'contract');
                                }}
                                className="text-gray-500 hover:text-cyan-400 transition-colors shrink-0"
                                title="Copy contract address"
                            >
                                {copied === 'contract' ? (
                                    <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                    </svg>
                                ) : (
                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                    </svg>
                                )}
                            </button>
                            <a
                                href={`https://sepolia.starkscan.co/contract/${wallet.contract_address}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="text-gray-500 hover:text-cyan-400 transition-colors shrink-0"
                                title="View on Starkscan"
                            >
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                </svg>
                            </a>
                        </div>
                    </div>
                )}

                {/* Identity Hash */}
                <div>
                    <span className="text-gray-500 text-xs">Identity Hash</span>
                    <div className="flex items-center gap-2 mt-0.5">
                        <p className="text-gray-300 font-mono text-xs break-all flex-1">
                            {identityHash ? identityHash.slice(0, 24) + '...' : 'N/A'}
                        </p>
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                if (identityHash) {
                                    copyToClipboard(identityHash, 'hash');
                                }
                            }}
                            className="text-gray-500 hover:text-white transition-colors shrink-0"
                            title="Copy identity hash"
                        >
                            {copied === 'hash' ? (
                                <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                            ) : (
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                </svg>
                            )}
                        </button>
                    </div>
                </div>

                {wallet.created_at && (
                    <div>
                        <span className="text-gray-500 text-xs">Created</span>
                        <p className="text-gray-300 text-xs mt-0.5">
                            {new Date(wallet.created_at * 1000).toLocaleDateString()}
                        </p>
                    </div>
                )}

                {/* Failed deploy — retry button */}
                {isFailed && (
                    <div className="pt-2">
                        <button
                            onClick={handleRetryDeploy}
                            disabled={deploying}
                            className="w-full px-3 py-2 bg-red-900/30 border border-red-500/30 text-red-300 rounded-lg text-xs hover:bg-red-900/50 transition-colors disabled:opacity-50"
                        >
                            {deploying ? 'Deploying...' : 'Retry Contract Deployment'}
                        </button>
                        {deployError && (
                            <p className="text-red-400 text-xs mt-1">{deployError}</p>
                        )}
                    </div>
                )}

                {/* Action Buttons for deployed wallets */}
                {isDeployed && showActions && (
                    <div className="flex gap-2 pt-2">
                        <Link
                            to={`/send?wallet=${wallet.user_id || wallet.label}`}
                            onClick={(e) => e.stopPropagation()}
                            className="flex-1 px-3 py-2 bg-indigo-600/20 border border-indigo-500/30 text-indigo-300 rounded-lg text-xs text-center hover:bg-indigo-600/40 transition-colors"
                        >
                            Send STRK
                        </Link>
                        <Link
                            to={`/receive?wallet=${wallet.user_id || wallet.label}`}
                            onClick={(e) => e.stopPropagation()}
                            className="flex-1 px-3 py-2 bg-cyan-600/20 border border-cyan-500/30 text-cyan-300 rounded-lg text-xs text-center hover:bg-cyan-600/40 transition-colors"
                        >
                            Receive
                        </Link>
                    </div>
                )}
            </div>
        </div>
    );
}
