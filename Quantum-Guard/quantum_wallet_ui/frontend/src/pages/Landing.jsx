import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Card from "../components/Card";
import Button from "../components/Button";
import { createOrg, setApiKey, clearApiKey, listWallets } from "../api/client";

export default function Landing() {
    const navigate = useNavigate();
    const [apiKeyInput, setApiKeyInput] = useState("");
    const [loginLoading, setLoginLoading] = useState(false);
    const [loginError, setLoginError] = useState(null);
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

    async function onLogin(event) {
        event.preventDefault();
        setLoginLoading(true);
        setLoginError(null);

        try {
            const key = apiKeyInput.trim();
            if (!key) {
                throw new Error("Please enter an API key");
            }

            setApiKey(key);
            await listWallets(1, 0);
            navigate("/dashboard");
        } catch (err) {
            clearApiKey();
            setLoginError(
                err.readableMessage ||
                err.response?.data?.detail ||
                err.message ||
                "Login failed"
            );
        } finally {
            setLoginLoading(false);
        }
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
        <div className="min-h-screen bg-bg-dark text-white px-6 py-10">
            <div className="max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-8">
                <Card variant="neon" title="Login">
                    <form onSubmit={onLogin} className="space-y-4">
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Organization API Key</label>
                            <input
                                type="password"
                                value={apiKeyInput}
                                onChange={(e) => setApiKeyInput(e.target.value)}
                                placeholder="Paste your API key"
                                required
                                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 font-mono text-sm"
                            />
                        </div>
                        <Button type="submit" disabled={loginLoading} className="w-full justify-center">
                            {loginLoading ? "Verifying..." : "Login"}
                        </Button>
                    </form>
                    {loginError && <p className="text-red-400 text-sm mt-4">{loginError}</p>}
                    <p className="text-xs text-gray-400 mt-4">
                        If you already have a key, only this login form is needed.
                    </p>
                </Card>

                <Card variant="default" title="Create Organization (Optional)">
                    <form onSubmit={onCreateOrg} className="space-y-4">
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Organization Name</label>
                            <input
                                type="text"
                                name="org_name"
                                value={form.org_name}
                                onChange={onChange}
                                required
                                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2"
                            />
                        </div>
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Admin Email</label>
                            <input
                                type="email"
                                name="admin_email"
                                value={form.admin_email}
                                onChange={onChange}
                                required
                                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2"
                            />
                        </div>
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Bootstrap Secret</label>
                            <input
                                type="password"
                                name="bootstrap_secret"
                                value={form.bootstrap_secret}
                                onChange={onChange}
                                required
                                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2"
                            />
                        </div>

                        <Button type="submit" disabled={loading} className="w-full justify-center">
                            {loading ? "Creating..." : "Create Organization"}
                        </Button>
                    </form>

                    {error && <p className="text-red-400 text-sm mt-4">{error}</p>}

                    {created?.api_key && (
                        <div className="mt-5 p-4 rounded-lg border border-neon-cyan/30 bg-neon-cyan/5">
                            <p className="text-xs text-gray-300 mb-2">Your API key (save securely):</p>
                            <p className="font-mono text-xs break-all text-neon-cyan">{created.api_key}</p>
                            <div className="flex gap-2 mt-3">
                                <Button type="button" onClick={copyKey} variant="secondary">
                                    Copy Key
                                </Button>
                                <Button type="button" onClick={useCreatedKeyAndContinue}>
                                    Use Key & Open Dashboard
                                </Button>
                            </div>
                        </div>
                    )}
                </Card>
            </div>
        </div>
    );
}
