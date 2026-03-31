import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createOrg, setApiKey } from "../api/client";

export default function Signup() {
    const navigate = useNavigate();
    const [form, setForm] = useState({
        org_name: "",
        admin_email: "",
        bootstrap_secret: "",
    });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [created, setCreated] = useState(null);

    function onChange(event) {
        setForm((prev) => ({ ...prev, [event.target.name]: event.target.value }));
    }

    async function onCreateOrg(event) {
        event.preventDefault();
        setLoading(true);
        setError(null);

        try {
            const res = await createOrg(form);
            const payload = res.data;
            setCreated(payload);
        } catch (err) {
            setError(
                err.readableMessage ||
                err.response?.data?.detail ||
                err.message ||
                "Failed to create organization"
            );
        } finally {
            setLoading(false);
        }
    }

    function useCreatedKeyAndContinue() {
        if (!created?.api_key) return;
        setApiKey(created.api_key);
        navigate("/dashboard");
    }

    async function copyKey() {
        if (!created?.api_key) return;
        await navigator.clipboard.writeText(created.api_key);
    }

    return (
        <div className="min-h-screen bg-black text-white font-sans flex flex-col justify-center items-center p-6 selection:bg-blue-500 selection:text-white">
            
            {/* Logo / Brand */}
            <Link to="/" className="flex items-center gap-3 mb-10 group cursor-pointer">
                <div className="w-10 h-10 bg-white text-black flex items-center justify-center rounded-xl font-extrabold text-[14px] tracking-tighter group-hover:scale-105 transition-transform duration-300">Zen</div>
                <span className="font-bold text-2xl tracking-tight text-white group-hover:text-gray-200 transition-colors">ZENTROPY</span>
            </Link>

            {/* Signup Card */}
            <div className="w-full max-w-[420px] bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-8 md:p-10 shadow-2xl">
                <div className="text-center mb-10">
                    <h1 className="text-2xl font-bold tracking-tight mb-2">Create Organization</h1>
                    <p className="text-gray-400 text-sm">Initialize your root namespace on the Zentropy backend.</p>
                </div>

                <form onSubmit={onCreateOrg} className="space-y-5">
                    <div className="space-y-2">
                        <label className="block text-[13px] font-medium text-gray-400 ml-1">Organization Name</label>
                        <input
                            type="text"
                            name="org_name"
                            value={form.org_name}
                            onChange={onChange}
                            placeholder="Acme Corp"
                            required
                            className="w-full bg-[#111] border border-[#222] focus:border-[#444] rounded-xl px-4 py-3.5 text-[14px] text-white placeholder-gray-600 outline-none transition-all"
                        />
                    </div>
                    <div className="space-y-2">
                        <label className="block text-[13px] font-medium text-gray-400 ml-1">Admin Email</label>
                        <input
                            type="email"
                            name="admin_email"
                            value={form.admin_email}
                            onChange={onChange}
                            placeholder="admin@example.com"
                            required
                            className="w-full bg-[#111] border border-[#222] focus:border-[#444] rounded-xl px-4 py-3.5 text-[14px] text-white placeholder-gray-600 outline-none transition-all"
                        />
                    </div>
                    <div className="space-y-2">
                        <label className="block text-[13px] font-medium text-gray-400 ml-1">Bootstrap Secret</label>
                        <input
                            type="password"
                            name="bootstrap_secret"
                            value={form.bootstrap_secret}
                            onChange={onChange}
                            placeholder="••••••••"
                            required
                            className="w-full bg-[#111] border border-[#222] focus:border-[#444] rounded-xl px-4 py-3.5 text-[14px] text-white placeholder-gray-600 outline-none transition-all"
                        />
                        <p className="text-[12px] text-gray-500 mt-2 ml-1 text-center sm:text-left">
                            If you don't have the secret please{" "}
                            <a href="https://zentropy-docs.vercel.app/ZENTROPY_ANALYSIS#bootstrap-secret" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 font-medium transition-colors underline underline-offset-2">
                                click here
                            </a>
                        </p>
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
                                Initializing...
                            </span>
                        ) : "Create Organization"}
                    </button>
                </form>

                {created?.api_key && (
                    <div className="mt-6 p-5 rounded-xl border border-blue-500/30 bg-blue-500/5 animate-fade-in-up">
                        <p className="text-[13px] text-gray-400 mb-2 font-medium">Your API key (save securely):</p>
                        <div className="bg-[#111] border border-[#222] p-3 rounded-lg mb-4">
                            <p className="font-mono text-[13px] break-all text-blue-400">{created.api_key}</p>
                        </div>
                        <div className="flex flex-col gap-3">
                            <button 
                                type="button" 
                                onClick={copyKey} 
                                className="w-full py-2.5 rounded-lg border border-[#333] hover:bg-[#1a1a1a] transition-colors text-sm font-medium"
                            >
                                Copy Key
                            </button>
                            <button 
                                type="button" 
                                onClick={useCreatedKeyAndContinue}
                                className="w-full py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 transition-colors text-sm font-semibold shadow-lg shadow-blue-600/20"
                            >
                                Use Key & Open Dashboard
                            </button>
                        </div>
                    </div>
                )}
                
                <div className="mt-8 pt-6 border-t border-[#1a1a1a] text-center">
                    <p className="text-[14px] text-gray-500">
                        Already have a key?{" "}
                        <Link to="/login" className="text-white hover:text-blue-400 font-medium transition-colors">
                            Login here
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
}
