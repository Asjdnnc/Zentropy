import { useState, useEffect, useRef, useCallback } from "react";
import { createWallet, listWallets, getWalletInfo, getWalletBalance } from "../api/client";
import { useWallet } from "../context/WalletContext";
import WalletCard from "../components/WalletCard";
import Card from "../components/Card";
import Button from "../components/Button";

export default function CreateWallet() {
    const [label, setLabel] = useState("");
    const [wallets, setWallets] = useState([]);
    const [balances, setBalances] = useState({});
    const [selected, setSelected] = useState(null);
    const [creating, setCreating] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const { refreshAll } = useWallet();

    // Camera state
    const [cameraActive, setCameraActive] = useState(false);
    const [capturedPhoto, setCapturedPhoto] = useState(null);
    const [cameraError, setCameraError] = useState(null);
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const streamRef = useRef(null);

    useEffect(() => {
        fetchWallets();
        return () => stopCamera();
    }, []);

    async function fetchWallets() {
        try {
            const res = await listWallets();
            const w = res.data.wallets || [];
            setWallets(w);
            const deployed = w.filter(wallet => wallet.contract_address);
            const balanceResults = await Promise.all(
                deployed.map(wallet =>
                    getWalletBalance(wallet.label).then(r => ({ label: wallet.label, data: r.data })).catch(() => null)
                )
            );
            const newBalances = {};
            balanceResults.forEach(b => {
                if (b) newBalances[b.label] = b.data;
            });
            setBalances(newBalances);
        } catch {
            // API might be offline
        }
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
            if (videoRef.current) {
                videoRef.current.srcObject = stream;
                await videoRef.current.play();
            }
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
        setCreating(true);
        setError(null);
        setResult(null);

        try {
            const walletLabel = label.trim() || "default";
            // Send photo to backend (if captured). All entropy processing happens server-side.
            const res = await createWallet(walletLabel, capturedPhoto || "");
            setResult(res.data);
            setLabel("");
            setCapturedPhoto(null);
            await fetchWallets();
            await refreshAll();
        } catch (err) {
            setError(
                err.response?.data?.detail || err.message || "Failed to create wallet",
            );
        } finally {
            setCreating(false);
        }
    }

    async function handleSelect(wallet) {
        try {
            const res = await getWalletInfo(wallet.label);
            setSelected(res.data);
        } catch (err) {
            setError(err.response?.data?.detail || "Failed to load wallet info");
        }
    }

    const copyToClipboard = async (text) => {
        try { await navigator.clipboard.writeText(text); } catch { }
    };

    return (
        <div className="space-y-8 animate-fade-in">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h1 className="text-3xl font-bold font-orbitron text-white">
                        Wallet Management
                    </h1>
                    <p className="text-gray-400 mt-1">
                        Create quantum-resistant wallets — each auto-deployed to Starknet Sepolia
                    </p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Create Wallet Form */}
                <Card variant="neon" title="Initialize New Wallet" className="h-fit">
                    <form onSubmit={handleCreate} className="space-y-4">
                        <div>
                            <label className="block text-xs font-orbitron text-gray-400 mb-2 uppercase">
                                Wallet Label
                            </label>
                            <input
                                type="text"
                                value={label}
                                onChange={(e) => setLabel(e.target.value)}
                                placeholder="e.g. primary-vault"
                                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-neon-cyan/50 focus:shadow-[0_0_15px_rgba(0,243,255,0.1)] transition-all"
                            />
                        </div>

                        {/* Camera Section */}
                        <div className="space-y-3">
                            <label className="block text-xs font-orbitron text-gray-400 uppercase">
                                Identity Verification
                            </label>

                            {!cameraActive && !capturedPhoto && (
                                <div className="text-center">
                                    <button
                                        type="button"
                                        onClick={startCamera}
                                        className="w-full p-4 border border-dashed border-white/20 rounded-lg hover:border-neon-cyan/50 hover:bg-white/5 transition-all group"
                                    >
                                        <svg className="w-8 h-8 mx-auto text-gray-500 group-hover:text-neon-cyan transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                                        </svg>
                                        <span className="block text-xs text-gray-500 group-hover:text-gray-300 mt-2 transition-colors">
                                            Tap to capture photo for secure key generation
                                        </span>
                                    </button>
                                </div>
                            )}

                            {cameraActive && (
                                <div className="relative rounded-lg overflow-hidden border border-neon-cyan/30">
                                    <video
                                        ref={videoRef}
                                        autoPlay
                                        playsInline
                                        muted
                                        className="w-full rounded-lg"
                                    />
                                    <div className="absolute inset-0 border-2 border-neon-cyan/20 rounded-lg pointer-events-none">
                                        {/* Corner brackets for camera feel */}
                                        <div className="absolute top-2 left-2 w-6 h-6 border-t-2 border-l-2 border-neon-cyan/60"></div>
                                        <div className="absolute top-2 right-2 w-6 h-6 border-t-2 border-r-2 border-neon-cyan/60"></div>
                                        <div className="absolute bottom-2 left-2 w-6 h-6 border-b-2 border-l-2 border-neon-cyan/60"></div>
                                        <div className="absolute bottom-2 right-2 w-6 h-6 border-b-2 border-r-2 border-neon-cyan/60"></div>
                                    </div>
                                    <div className="absolute bottom-3 left-0 right-0 flex justify-center gap-3">
                                        <button
                                            type="button"
                                            onClick={capturePhoto}
                                            className="px-4 py-2 bg-neon-cyan/90 text-black font-bold rounded-lg text-sm hover:bg-neon-cyan transition-colors"
                                        >
                                            Capture
                                        </button>
                                        <button
                                            type="button"
                                            onClick={stopCamera}
                                            className="px-4 py-2 bg-white/10 text-white rounded-lg text-sm hover:bg-white/20 transition-colors"
                                        >
                                            Cancel
                                        </button>
                                    </div>
                                </div>
                            )}

                            {capturedPhoto && (
                                <div className="relative rounded-lg overflow-hidden border border-neon-green/30">
                                    <img
                                        src={capturedPhoto}
                                        alt="Captured"
                                        className="w-full rounded-lg opacity-80"
                                    />
                                    <div className="absolute top-2 right-2">
                                        <span className="px-2 py-1 bg-neon-green/20 text-neon-green text-xs rounded-full border border-neon-green/30">
                                            Captured
                                        </span>
                                    </div>
                                    <div className="absolute bottom-3 left-0 right-0 flex justify-center">
                                        <button
                                            type="button"
                                            onClick={retakePhoto}
                                            className="px-4 py-2 bg-white/10 text-white rounded-lg text-sm hover:bg-white/20 transition-colors"
                                        >
                                            Retake
                                        </button>
                                    </div>
                                </div>
                            )}

                            {cameraError && (
                                <p className="text-yellow-400 text-xs">{cameraError}</p>
                            )}

                            <canvas ref={canvasRef} className="hidden" />
                        </div>

                        <Button
                            type="submit"
                            disabled={creating}
                            variant="primary"
                            className="w-full justify-center"
                        >
                            {creating ? (
                                <span className="flex items-center gap-2">
                                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                                    Generating & Deploying...
                                </span>
                            ) : (
                                capturedPhoto
                                    ? "Create with Photo Verification"
                                    : "Create & Deploy Wallet"
                            )}
                        </Button>

                        <div className="text-xs text-center text-gray-500 font-mono mt-4 space-y-1">
                            <div>Algorithm: ML-DSA-44 (Dilithium)</div>
                            <div>Network: Starknet Sepolia</div>
                            {capturedPhoto && (
                                <div className="text-neon-green/70">Photo will be used for secure key generation</div>
                            )}
                        </div>
                    </form>
                </Card>

                {/* Status/Result Display */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Active Result */}
                    {result && (
                        <Card
                            variant="default"
                            className={`border-l-4 relative overflow-hidden ${result.deployment_status === 'deployed'
                                ? 'border-l-neon-green'
                                : result.deployment_status === 'failed'
                                    ? 'border-l-yellow-500'
                                    : 'border-l-blue-500'
                                }`}
                        >
                            <div className="absolute top-0 right-0 p-4 opacity-5 pointer-events-none">
                                <svg className="w-32 h-32 text-neon-green" fill="currentColor" viewBox="0 0 24 24">
                                    <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                            </div>

                            <h3 className="text-neon-green font-orbitron font-bold mb-4 flex items-center gap-2">
                                <span className="w-2 h-2 bg-neon-green rounded-full animate-pulse"></span>
                                {result.deployment_status === 'deployed'
                                    ? 'WALLET DEPLOYED'
                                    : 'IDENTITY CREATED'}
                            </h3>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm relative z-10">
                                <div className="p-3 bg-black/20 rounded-lg">
                                    <span className="text-gray-500 block text-xs mb-1 uppercase tracking-wider">Label</span>
                                    <span className="text-white font-mono">{result.label}</span>
                                </div>
                                <div className="p-3 bg-black/20 rounded-lg">
                                    <span className="text-gray-500 block text-xs mb-1 uppercase tracking-wider">Algorithm</span>
                                    <span className="text-white font-mono">{result.algorithm}</span>
                                </div>
                                <div className="p-3 bg-black/20 rounded-lg md:col-span-2">
                                    <span className="text-gray-500 block text-xs mb-1 uppercase tracking-wider">Identity Hash</span>
                                    <span className="text-neon-cyan font-mono text-xs break-all">{result.pubkey_hash}</span>
                                </div>

                                {/* Seed verification badge — no technical details, just a trust indicator */}
                                {result.seed_verified && (
                                    <div className="p-3 bg-neon-green/5 rounded-lg md:col-span-2 border border-neon-green/20">
                                        <div className="flex items-center gap-2">
                                            <svg className="w-4 h-4 text-neon-green" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                                            </svg>
                                            <span className="text-neon-green text-xs font-mono">Secured with enhanced key generation</span>
                                        </div>
                                    </div>
                                )}

                                {/* Contract Address */}
                                {result.contract_address && (
                                    <div className="p-3 bg-black/20 rounded-lg md:col-span-2 border border-green-500/20">
                                        <span className="text-gray-500 block text-xs mb-1 uppercase tracking-wider">
                                            Contract Address (Starknet Sepolia)
                                        </span>
                                        <div className="flex items-center gap-2">
                                            <span className="text-green-400 font-mono text-xs break-all flex-1">
                                                {result.contract_address}
                                            </span>
                                            <button
                                                onClick={() => copyToClipboard(result.contract_address)}
                                                className="text-gray-400 hover:text-green-400 transition-colors"
                                                title="Copy address"
                                            >
                                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                                </svg>
                                            </button>
                                            <a
                                                href={result.explorer_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="text-gray-400 hover:text-green-400 transition-colors"
                                                title="View on Starkscan"
                                            >
                                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                                </svg>
                                            </a>
                                        </div>
                                    </div>
                                )}

                                {/* Deployment failed warning */}
                                {result.deployment_status === 'failed' && (
                                    <div className="p-3 bg-yellow-900/20 rounded-lg md:col-span-2 border border-yellow-500/20">
                                        <span className="text-yellow-400 text-xs">
                                            Identity created but contract deployment failed: {result.deployment_error}
                                        </span>
                                        <p className="text-yellow-500/70 text-xs mt-1">
                                            You can retry deployment from the wallet card below.
                                        </p>
                                    </div>
                                )}
                            </div>
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

                    {/* Wallets List / Details */}
                    {selected ? (
                        <Card title={`Wallet: ${selected.label}`} className="h-full">
                            <div className="flex justify-between items-start mb-6">
                                <div className="text-xs text-gray-400 font-mono">
                                    STATUS: {selected.deployment_status?.toUpperCase() || 'UNKNOWN'}
                                </div>
                                <button
                                    onClick={() => setSelected(null)}
                                    className="text-gray-400 hover:text-white transition-colors"
                                >
                                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                    </svg>
                                </button>
                            </div>

                            <div className="space-y-4">
                                {/* Contract Address */}
                                {selected.contract_address && (
                                    <div>
                                        <span className="text-gray-500 text-xs font-orbitron uppercase tracking-wider">
                                            Contract Address
                                        </span>
                                        <div className="mt-1 p-4 bg-black/40 rounded-lg border border-green-500/10 font-mono text-xs text-green-400 break-all leading-relaxed">
                                            {selected.contract_address}
                                        </div>
                                    </div>
                                )}

                                <div>
                                    <span className="text-gray-500 text-xs font-orbitron uppercase tracking-wider">
                                        Public Key Preview
                                    </span>
                                    <div className="mt-1 p-4 bg-black/40 rounded-lg border border-white/5 font-mono text-xs text-gray-300 break-all leading-relaxed">
                                        {selected.public_key_preview || "Generating preview..."}
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="p-3 bg-white/5 rounded-lg border border-white/5">
                                        <span className="text-gray-500 text-xs block mb-1">KEY SIZE</span>
                                        <span className="text-white font-mono">{selected.public_key_size} bytes</span>
                                    </div>
                                    <div className="p-3 bg-white/5 rounded-lg border border-white/5">
                                        <span className="text-gray-500 text-xs block mb-1">STATUS</span>
                                        <span className={`font-mono ${selected.deployment_status === 'deployed' ? 'text-neon-green' : 'text-yellow-400'}`}>
                                            {selected.deployment_status === 'deployed' ? 'DEPLOYED' : selected.deployment_status?.toUpperCase() || 'PENDING'}
                                        </span>
                                    </div>
                                </div>

                                {selected.explorer_url && (
                                    <a
                                        href={selected.explorer_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="block p-3 bg-indigo-900/20 border border-indigo-500/20 rounded-lg text-indigo-300 text-xs text-center hover:bg-indigo-900/40 transition-colors"
                                    >
                                        View on Starkscan Explorer
                                    </a>
                                )}
                            </div>
                        </Card>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {wallets.length === 0 ? (
                                <div className="col-span-2 text-center py-12 text-gray-500 italic">
                                    No wallets detected. Initialize one to proceed.
                                </div>
                            ) : (
                                wallets.map((w) => (
                                    <WalletCard
                                        key={w.label}
                                        wallet={w}
                                        balance={balances[w.label]}
                                        onSelect={handleSelect}
                                        className="cursor-pointer hover:border-neon-purple/50 transition-all"
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
