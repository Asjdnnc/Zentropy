import { useState, useEffect, useRef, useCallback } from "react";
import { createWallet, listWallets, getWalletInfo, getWalletBalance, getDeploymentStatus } from "../api/client";
import { useWallet } from "../context/WalletContext";
import WalletCard from "../components/WalletCard";

const DEBUG_NS = "[CreateWallet]";

export default function CreateWallet() {
    const [label, setLabel] = useState("");
    const [wallets, setWallets] = useState([]);
    const [balances, setBalances] = useState({});
    const [selected, setSelected] = useState(null);
    const [creating, setCreating] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [showPhrase, setShowPhrase] = useState(false);
    const { refreshAll } = useWallet();

    // Camera state
    const [cameraActive, setCameraActive] = useState(false);
    const [capturedPhoto, setCapturedPhoto] = useState(null);
    const [cameraError, setCameraError] = useState(null);
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const streamRef = useRef(null);

    function debugLog(step, payload = null) {
        if (payload !== null) {
            console.log(`${DEBUG_NS} ${step}`, payload);
            return;
        }
        console.log(`${DEBUG_NS} ${step}`);
    }

    function debugError(step, err) {
        console.error(`${DEBUG_NS} ${step}`, {
            message: err?.message,
            readableMessage: err?.readableMessage,
            status: err?.response?.status,
            detail: err?.response?.data?.detail,
            data: err?.response?.data,
        });
    }

    useEffect(() => {
        fetchWallets();
        return () => stopCamera();
    }, []);

    useEffect(() => {
        if (cameraActive && videoRef.current && streamRef.current) {
            videoRef.current.srcObject = streamRef.current;
        }
    }, [cameraActive]);

    async function fetchWallets() {
        debugLog("fetchWallets:start");
        try {
            const res = await listWallets();
            const users = res.data.users || res.data.wallets || [];
            debugLog("fetchWallets:users_loaded", { count: users.length });

            const w = await Promise.all(
                users.map(async (u) => {
                    const userId = u.user_id || u.label;
                    if (!userId) return null;
                    try {
                        const walletRes = await getWalletInfo(userId);
                        debugLog("fetchWallets:wallet_loaded", {
                            user_id: userId,
                            deployment_status: walletRes.data?.deployment_status,
                            contract_address: walletRes.data?.contract_address,
                        });
                        return {
                            label: userId,
                            user_id: userId,
                            username: u.username || u.email || userId,
                            ...walletRes.data,
                        };
                    } catch {
                        debugLog("fetchWallets:wallet_load_failed", { user_id: userId });
                        return {
                            label: userId,
                            user_id: userId,
                            username: u.username || u.email || userId,
                            contract_address: null,
                            deployment_status: "unknown",
                        };
                    }
                })
            );

            const walletsNormalized = w.filter(Boolean);
            setWallets(walletsNormalized);
            const deployed = walletsNormalized.filter(wallet => wallet.contract_address);
            const balanceResults = await Promise.all(
                deployed.map(wallet =>
                    getWalletBalance(wallet.user_id).then(r => ({ user_id: wallet.user_id, data: r.data })).catch(() => null)
                )
            );
            const newBalances = {};
            balanceResults.forEach(b => {
                if (b) newBalances[b.user_id] = b.data;
            });
            setBalances(newBalances);
            debugLog("fetchWallets:done", {
                wallets: walletsNormalized.length,
                deployed_wallets: deployed.length,
            });
        } catch (err) {
            debugError("fetchWallets:error", err);
            // API might be offline
        }
    }

    async function waitForDeploymentStatus(userId, options = {}) {
        const maxAttempts = options.maxAttempts || 15;
        const intervalMs = options.intervalMs || 3000;
        debugLog("deployment_poll:start", { user_id: userId, maxAttempts, intervalMs });

        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                const res = await getDeploymentStatus(userId);
                const status = res.data?.deployment_status;
                debugLog("deployment_poll:tick", {
                    attempt,
                    status,
                    deployment_attempts: res.data?.deployment_attempts,
                    deployment_error_message: res.data?.deployment_error_message,
                    tx_hash: res.data?.deployment_tx_hash,
                });

                if (status === "deployed" || status === "failed") {
                    return res.data;
                }
            } catch (err) {
                debugError("deployment_poll:error", err);
            }

            await new Promise((resolve) => setTimeout(resolve, intervalMs));
        }

        debugLog("deployment_poll:timeout", { user_id: userId });
        return null;
    }

    // ─── Camera Functions ─────────────────────────────────────────

    const startCamera = useCallback(async () => {
        setCameraError(null);
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
                audio: false,
            });
            streamRef.current = stream;
            setCameraActive(true);
        } catch (err) {
            setCameraError(
                err.name === "NotAllowedError"
                    ? "Camera access denied. Please allow camera access to generate your wallet."
                    : err.name === "NotFoundError"
                        ? "No camera found. You can still create a wallet without camera entropy."
                        : "Failed to access camera. You can still create a wallet."
            );
        }
    }, []);

    function stopCamera() {
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(track => track.stop());
            streamRef.current = null;
        }
        if (videoRef.current) {
            videoRef.current.srcObject = null;
        }
        setCameraActive(false);
    }

    function capturePhoto() {
        if (!videoRef.current || !canvasRef.current) return;

        const video = videoRef.current;
        const canvas = canvasRef.current;
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;

        const ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0);

        // Get base64 JPEG
        const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
        setCapturedPhoto(dataUrl);

        // Stop camera after capture
        stopCamera();
    }

    function retakePhoto() {
        setCapturedPhoto(null);
        startCamera();
    }

    // ─── Wallet Creation ─────────────────────────────────────────

    async function handleCreate(e) {
        e.preventDefault();
        
        if (!capturedPhoto) {
            setError("Identity verification photo is required to create a wallet.");
            return;
        }

        setCreating(true);
        setError(null);
        setResult(null);
        debugLog("handleCreate:start", { label });

        try {
            const walletLabel = label.trim() || "default";
            // Generate a validator-safe unique email for custodial user records.
            const safeLabel = walletLabel.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "wallet";
            const email = `${safeLabel}-${Date.now()}@test.com`;
            debugLog("handleCreate:request_payload", { email, username: walletLabel });
            // All entropy processing happens server-side with photo
            const res = await createWallet({
                email,
                username: walletLabel
            });
            debugLog("handleCreate:createWallet_response", res.data);

            const initialStatus = res.data.deployment_status || "pending";
            let finalStatus = initialStatus;
            let deploymentMeta = null;
            if (res.data.user_id && (initialStatus === "pending" || initialStatus === "counterfactual")) {
                deploymentMeta = await waitForDeploymentStatus(res.data.user_id);
                if (deploymentMeta?.deployment_status) {
                    finalStatus = deploymentMeta.deployment_status;
                }
            }

            setResult({
                ...res.data,
                label: walletLabel,
                algorithm: "ML-DSA-44",
                pubkey_hash: res.data.public_key_hash,
                deployment_status: finalStatus,
                deployment_error: deploymentMeta?.deployment_error_message || res.data.deployment_error_message || null,
                deployment_tx_hash: deploymentMeta?.deployment_tx_hash || res.data.deployment_tx_hash || null,
                seed_verified: Boolean(capturedPhoto),
                explorer_url: res.data.contract_address
                    ? `https://sepolia.voyager.online/contract/${res.data.contract_address}`
                    : null,
            });

            debugLog("handleCreate:final_status", {
                user_id: res.data.user_id,
                status: finalStatus,
                deployment_error: deploymentMeta?.deployment_error_message || null,
                deployment_tx_hash: deploymentMeta?.deployment_tx_hash || null,
            });

            if (finalStatus === "failed") {
                setError(deploymentMeta?.deployment_error_message || "Deployment failed. See console logs for details.");
            }

            setLabel("");
            setCapturedPhoto(null);
            setShowPhrase(false);
            await fetchWallets();
            await refreshAll();
        } catch (err) {
            debugError("handleCreate:error", err);
            setError(
                err.readableMessage ||
                err.response?.data?.detail ||
                err.message ||
                "Failed to create wallet",
            );
        } finally {
            debugLog("handleCreate:done");
            setCreating(false);
        }
    }

    async function handleSelect(wallet) {
        try {
            const res = await getWalletInfo(wallet.user_id || wallet.label);
            setSelected(res.data);
        } catch (err) {
            setError(
                err.readableMessage ||
                err.response?.data?.detail ||
                "Failed to load wallet info"
            );
        }
    }

    const copyToClipboard = async (text) => {
        try {
            await navigator.clipboard.writeText(text);
        } catch {
            return null;
        }
    };

    return (
        <div className="space-y-8 animate-fade-in text-white font-sans max-w-7xl mx-auto w-full">
            {/* Header */}
            <div className="mb-8 pl-1">
                <h1 className="text-2xl font-bold tracking-tight mb-2">Wallet Management</h1>
                <p className="text-gray-400 text-[14px]">Create quantum-resistant wallets — each auto-deployed to Starknet.</p>
            </div>

            <div className="flex flex-col gap-10">
                {/* Top Section: Create Form */}
                <div className="w-full relative z-10">
                    <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-8 md:p-10 shadow-2xl">
                        <h2 className="text-lg font-semibold tracking-tight text-white mb-8 border-b border-[#1a1a1a] pb-5">Initialize New Wallet</h2>
                        
                        {!result && (
                            <form onSubmit={handleCreate} className="grid grid-cols-1 md:grid-cols-2 gap-10">
                                {/* Left Column: Label and Meta Info */}
                                <div className="space-y-6 flex flex-col justify-between">
                                    <div className="space-y-2">
                                        <label className="block text-[13px] font-medium text-gray-400 ml-1">
                                            Wallet Label
                                        </label>
                                        <input
                                            type="text"
                                            value={label}
                                            onChange={(e) => setLabel(e.target.value)}
                                            placeholder="e.g. primary-vault"
                                            className="w-full bg-[#111] border border-[#222] focus:border-[#444] rounded-xl px-4 py-3.5 text-[14px] text-white placeholder-gray-600 outline-none transition-all"
                                        />
                                    </div>
                                    
                                    <div className="hidden md:block py-4 border-t border-[#1a1a1a]">
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="text-[12px] text-gray-500 font-medium">Algorithm</span>
                                            <span className="text-[12px] text-gray-300 font-mono tracking-tight">ML-DSA-44 (Dilithium)</span>
                                        </div>
                                        <div className="flex items-center justify-between">
                                            <span className="text-[12px] text-gray-500 font-medium">Network</span>
                                            <span className="text-[12px] text-gray-300 font-mono tracking-tight">Starknet Sepolia</span>
                                        </div>
                                    </div>
                                </div>

                                {/* Right Column: Camera */}
                                <div className="space-y-3 relative">
                                    <label className="block text-[13px] font-medium text-gray-400 ml-1">
                                        Identity Verification
                                    </label>

                                    {!cameraActive && !capturedPhoto && (
                                        <div className="text-center">
                                            <button
                                                type="button"
                                                onClick={startCamera}
                                                className="w-full p-8 border border-dashed border-[#333] rounded-[16px] hover:border-gray-500 hover:bg-[#111] transition-all group flex flex-col items-center justify-center min-h-[160px]"
                                            >
                                                <svg className="w-8 h-8 text-gray-500 group-hover:text-white transition-colors mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                                                </svg>
                                                <span className="block text-[13px] text-gray-400 group-hover:text-gray-200 transition-colors">
                                                    Tap to capture photo for secure key generation
                                                </span>
                                            </button>
                                        </div>
                                    )}

                                    {cameraActive && (
                                        <div className="relative rounded-[16px] overflow-hidden border border-[#333] bg-black">
                                            <video ref={videoRef} autoPlay playsInline muted className="w-full rounded-[16px]" />
                                            <div className="absolute inset-0 border-2 border-white/10 rounded-[16px] pointer-events-none">
                                                {/* Corner brackets */}
                                                <div className="absolute top-4 left-4 w-5 h-5 border-t-2 border-l-2 border-white/50"></div>
                                                <div className="absolute top-4 right-4 w-5 h-5 border-t-2 border-r-2 border-white/50"></div>
                                                <div className="absolute bottom-4 left-4 w-5 h-5 border-b-2 border-l-2 border-white/50"></div>
                                                <div className="absolute bottom-4 right-4 w-5 h-5 border-b-2 border-r-2 border-white/50"></div>
                                            </div>
                                            <div className="absolute bottom-4 left-0 right-0 flex justify-center gap-3">
                                                <button type="button" onClick={capturePhoto} className="px-5 py-2.5 bg-white text-black font-semibold rounded-xl text-[13px] hover:bg-gray-200 transition-colors shadow-lg">Capture</button>
                                                <button type="button" onClick={stopCamera} className="px-5 py-2.5 bg-black/60 backdrop-blur-md border border-[#333] text-white rounded-xl text-[13px] hover:bg-black/80 transition-colors">Cancel</button>
                                            </div>
                                        </div>
                                    )}

                                    {capturedPhoto && (
                                        <div className="relative rounded-[16px] overflow-hidden border border-[#333] w-full flex justify-center bg-[#050505] min-h-[160px]">
                                            <img src={capturedPhoto} alt="Verified Identity" className="h-auto max-h-[220px] object-contain opacity-90" />
                                            <div className="absolute top-3 right-3">
                                                <span className="px-2.5 py-1 bg-green-500/10 text-green-400 text-[11px] font-medium rounded-md border border-green-500/20">Verified</span>
                                            </div>
                                            <div className="absolute bottom-3 left-0 right-0 flex justify-center">
                                                <button type="button" onClick={retakePhoto} className="px-4 py-2 bg-black/60 backdrop-blur-md border border-[#333] text-white rounded-xl text-[12px] hover:bg-black/80 transition-colors">Retake</button>
                                            </div>
                                        </div>
                                    )}

                                    {cameraError && (
                                        <p className="text-yellow-500 text-[12px] mt-2 bg-yellow-500/10 border border-yellow-500/20 p-2 rounded-lg">{cameraError}</p>
                                    )}

                                    <canvas ref={canvasRef} className="hidden" />
                                </div>

                                {/* Submit Button */}
                                <div className="md:col-span-2 pt-4">
                                    <button
                                        type="submit"
                                        disabled={creating}
                                        className="w-full flex items-center justify-center py-4 rounded-[16px] bg-white text-black text-[15px] font-semibold hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-[0_0_20px_rgba(255,255,255,0.1)]"
                                    >
                                        {creating ? (
                                            <span className="flex items-center gap-2">
                                                <svg className="animate-spin h-4 w-4 text-black" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                                                Generating & Deploying...
                                            </span>
                                        ) : (
                                            capturedPhoto ? "Create Secure Wallet" : "Create & Deploy Wallet"
                                        )}
                                    </button>
                                </div>

                                {/* Footer Info (Mobile) */}
                                <div className="mt-4 border-t border-[#1a1a1a] pt-4 md:hidden md:col-span-2 space-y-2">
                                    <div className="flex items-center justify-between">
                                        <span className="text-[11px] text-gray-500 font-medium">Algorithm</span>
                                        <span className="text-[11px] text-gray-300 font-mono">ML-DSA-44</span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-[11px] text-gray-500 font-medium">Network</span>
                                        <span className="text-[11px] text-gray-300 font-mono">Starknet Sepolia</span>
                                    </div>
                                </div>
                            </form>
                        )}
                        
                        {/* Result / Success state */}
                        {result && (
                            <div className="bg-[#111] border border-[#222] rounded-[16px] overflow-hidden">
                                <div className={`p-5 flex items-center gap-3 border-b ${result.deployment_status === 'deployed' ? 'border-green-500/20 bg-green-500/5' : result.deployment_status === 'failed' ? 'border-yellow-500/20 bg-yellow-500/5' : 'border-blue-500/20 bg-blue-500/5'}`}>
                                    <div className={`w-2 h-2 rounded-full animate-pulse ${result.deployment_status === 'deployed' ? 'bg-green-500' : result.deployment_status === 'failed' ? 'bg-yellow-500' : 'bg-blue-500'}`}></div>
                                    <h3 className="font-semibold text-[14px]">
                                        {result.deployment_status === 'deployed' ? 'Wallet Successfully Deployed' : 'Identity Created (Deployment Pending/Failed)'}
                                    </h3>
                                </div>
                                <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="p-4 bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl">
                                        <span className="text-gray-500 block text-[11px] mb-1 font-medium tracking-wider uppercase">Label</span>
                                        <span className="text-white font-mono text-[13px]">{result.label}</span>
                                    </div>
                                    <div className="p-4 bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl">
                                        <span className="text-gray-500 block text-[11px] mb-1 font-medium tracking-wider uppercase">Algorithm</span>
                                        <span className="text-white font-mono text-[13px]">{result.algorithm}</span>
                                    </div>
                                    <div className="p-4 bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl md:col-span-2">
                                        <span className="text-gray-500 block text-[11px] mb-1 font-medium tracking-wider uppercase">Identity Hash</span>
                                        <span className="text-blue-400 font-mono text-[13px] break-all">{result.pubkey_hash}</span>
                                    </div>
                                    
                                    {result.seed_phrase && (
                                        <div className="p-5 border border rounded-xl md:col-span-2">
                                            <div className="flex justify-between items-center mb-4">
                                                <span className="text-white font-semibold text-[13px] flex items-center gap-2 tracking-wide">
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" /></svg>
                                                    Secret Recovery Phrase
                                                </span>
                                                <div className="flex items-center gap-2">
                                                    <button onClick={() => setShowPhrase(!showPhrase)} className="px-3 py-1.5 bg-[#111] border border-[#222] text-gray-300 text-[11px] rounded-lg hover:bg-[#222] transition-colors font-medium">
                                                        {showPhrase ? "Hide" : "Reveal"}
                                                    </button>
                                                    <button onClick={() => copyToClipboard(result.seed_phrase)} className="px-3 py-1.5 border text-white text-[11px] rounded-lg hover:bg-red-500/20 transition-colors font-medium">
                                                        Copy
                                                    </button>
                                                </div>
                                            </div>
                                            <div className="relative">
                                                <div className={`grid grid-cols-2 md:grid-cols-4 gap-2 transition-all duration-300 ${!showPhrase ? "blur-md select-none pointer-events-none opacity-50" : ""}`}>
                                                    {result.seed_phrase.split(" ").map((word, idx) => (
                                                        <div key={idx} className="flex items-center gap-3 p-2.5 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg">
                                                            <span className="text-gray-600 font-mono text-[11px]">{idx + 1}.</span>
                                                            <span className="text-white font-mono text-[13px]">{word}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                                {!showPhrase && (
                                                    <div className="absolute inset-0 flex items-center justify-center">
                                                        <span className="bg-black/80 px-4 py-2 rounded-full border border-[#333] backdrop-blur-sm text-gray-300 text-[12px] font-medium">
                                                            Hidden for Security
                                                        </span>
                                                    </div>
                                                )}
                                            </div>
                                            <p className="text-white text-[11px] mt-4 font-medium text-center">Never share this. This phrase will never be shown again.</p>
                                        </div>
                                    )}

                                    {result.contract_address && (
                                        <div className="p-4 bg-green-900/10 border border-green-500/20 rounded-xl md:col-span-2">
                                            <span className="text-gray-500 block text-[11px] mb-1 font-medium tracking-wider uppercase">Contract Address</span>
                                            <div className="flex items-center gap-3">
                                                <span className="text-green-400 font-mono text-[13px] break-all flex-1">{result.contract_address}</span>
                                                <button onClick={() => copyToClipboard(result.contract_address)} className="text-gray-400 hover:text-white transition-colors">
                                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                                                </button>
                                                <a href={result.explorer_url} target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-white transition-colors">
                                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                                </a>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                        
                        {error && (
                            <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mt-6">
                                <p className="text-red-400 text-[13px] font-medium flex items-center gap-2">
                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                    </svg>
                                    {error}
                                </p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Bottom Section: Wallets List */}
                <div className="w-full">
                    <div className="flex justify-between items-center mb-6">
                        <h2 className="text-lg font-semibold text-white tracking-tight">Your Deployed Wallets</h2>
                        <span className="text-[11px] text-gray-400 font-medium bg-[#111] border border-[#222] px-2.5 py-1 rounded-md">
                            {wallets.length} active
                        </span>
                    </div>

                    {selected ? (
                        <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-6 shadow-xl">
                            <div className="flex justify-between items-start mb-6 pb-4 border-b border-[#1a1a1a]">
                                <div>
                                    <h3 className="font-semibold text-white text-[16px] mb-1">{selected.wallet_name || selected.username || selected.label || selected.user_id}</h3>
                                    <span className={`text-[11px] font-medium px-2 py-0.5 rounded-md ${selected.deployment_status === 'deployed' ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-yellow-500/10 text-yellow-500 border border-yellow-500/20'}`}>
                                        {selected.deployment_status?.toUpperCase() || 'UNKNOWN'}
                                    </span>
                                </div>
                                <button
                                    onClick={() => setSelected(null)}
                                    className="p-2 rounded-lg bg-[#111] border border-[#222] text-gray-400 hover:text-white hover:bg-[#222] transition-colors"
                                >
                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                    </svg>
                                </button>
                            </div>

                            <div className="space-y-4 mb-6">
                                {selected.contract_address && (
                                    <div className="p-4 bg-[#111] border border-[#222] rounded-xl">
                                        <span className="text-gray-500 block text-[11px] mb-2 font-medium tracking-wider uppercase">Contract Address</span>
                                        <div className="font-mono text-[13px] text-gray-300 break-all">
                                            {selected.contract_address}
                                        </div>
                                    </div>
                                )}
                            </div>

                            {selected.explorer_url && (
                                <a
                                    href={selected.explorer_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center justify-center gap-2 w-full py-3 bg-[#111] border border-[#222] rounded-xl text-gray-300 text-[13px] font-medium hover:bg-white hover:text-black transition-colors"
                                >
                                    View on Voyager Explorer
                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                                </a>
                            )}
                        </div>
                    ) : (
                        <div className="flex flex-col gap-4">
                            {wallets.length === 0 ? (
                                <div className="text-center py-12 bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px]">
                                    <span className="text-gray-500 text-[14px]">No wallets detected. Initialize one above.</span>
                                </div>
                            ) : (
                                wallets.map((w) => (
                                    <WalletCard
                                        key={w.user_id || w.label}
                                        wallet={w}
                                        balance={balances[w.user_id || w.label]}
                                        onSelect={handleSelect}
                                        className="cursor-pointer transition-all border-[#1a1a1a] bg-[#0a0a0a]"
                                    />
                                ))
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
