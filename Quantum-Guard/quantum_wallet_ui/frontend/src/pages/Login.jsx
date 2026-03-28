import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { setApiKey, clearApiKey, listWallets } from "../api/client";

export default function Login() {
    const navigate = useNavigate();
    const [apiKeyInput, setApiKeyInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    async function onSubmit(event) {
        event.preventDefault();
        setLoading(true);
        setError(null);

        try {
            const key = apiKeyInput.trim();
            if (!key) {
                throw new Error("Please enter an API key");
            }

            setApiKey(key);
            // Validate key using a protected endpoint (health is public and cannot verify auth).
            await listWallets(1, 0);
            navigate("/dashboard");
        } catch (err) {
            clearApiKey();
            setError(
                err.readableMessage ||
                err.response?.data?.detail ||
                (err.response?.status === 401
                    ? "Invalid API key for this backend environment. Create a new org on this same API URL and use that key."
                    : null) ||
                err.message ||
                "Login failed"
            );
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="min-h-screen bg-black text-white font-sans flex flex-col justify-center items-center p-6 selection:bg-blue-500 selection:text-white">
            
            {/* Logo / Brand */}
            <Link to="/" className="flex items-center gap-3 mb-10 group cursor-pointer">
                <div className="w-10 h-10 bg-white text-black flex items-center justify-center rounded-xl font-extrabold text-[14px] tracking-tighter group-hover:scale-105 transition-transform duration-300">Zen</div>
                <span className="font-bold text-2xl tracking-tight text-white group-hover:text-gray-200 transition-colors">ZENTROPY</span>
            </Link>

            {/* Login Card */}
            <div className="w-full max-w-[420px] bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-8 md:p-10 shadow-2xl">
                <div className="text-center mb-10">
                    <h1 className="text-2xl font-bold tracking-tight mb-2">Welcome back</h1>
                    <p className="text-gray-400 text-sm">Enter your organization API key to access your accounts.</p>
                </div>

                <form onSubmit={onSubmit} className="space-y-6">
                    <div className="space-y-2">
                        <label className="block text-[13px] font-medium text-gray-400 ml-1">Organization API Key</label>
                        <input
                            type="password"
                            value={apiKeyInput}
                            onChange={(e) => setApiKeyInput(e.target.value)}
                            placeholder="qg_live_xxxxxxxx..."
                            required
                            className="w-full bg-[#111] border border-[#222] focus:border-[#444] rounded-xl px-4 py-3.5 font-mono text-[14px] text-white placeholder-gray-600 outline-none transition-all placeholder:font-sans"
                        />
                    </div>
                    
                    {error && (
                        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-3 animate-fade-in-up">
                            <p className="text-red-400 text-[13px] text-center font-medium leading-relaxed">{error}</p>
                        </div>
                    )}

                    <button 
                        type="submit" 
                        disabled={loading} 
                        className="w-full flex items-center justify-center py-3.5 rounded-xl bg-white text-black text-[15px] font-semibold hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed mt-2"
                    >
                        {loading ? (
                            <span className="flex items-center gap-2">
                                <svg className="animate-spin h-4 w-4 text-black" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Verifying Security...
                            </span>
                        ) : "Access Dashboard"}
                    </button>
                </form>

                <div className="mt-8 pt-8 border-t border-[#1a1a1a] text-center">
                    <p className="text-[14px] text-gray-500">
                        Don't have a key?{" "}
                        <Link to="/signup" className="text-white hover:text-blue-400 font-medium transition-colors">
                            Create organization
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
}
