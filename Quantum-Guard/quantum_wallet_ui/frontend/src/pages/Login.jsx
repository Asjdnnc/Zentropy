import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Card from "../components/Card";
import Button from "../components/Button";
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
        <div className="min-h-screen bg-bg-dark text-white px-6 py-10 flex items-center justify-center">
            <Card variant="neon" title="Login With API Key" className="max-w-xl w-full">
                <form onSubmit={onSubmit} className="space-y-4">
                    <div>
                        <label className="block text-xs text-gray-400 mb-1">Organization API Key</label>
                        <input
                            type="password"
                            value={apiKeyInput}
                            onChange={(e) => setApiKeyInput(e.target.value)}
                            placeholder="Paste API key from org/create"
                            required
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 font-mono text-sm"
                        />
                    </div>
                    <Button type="submit" disabled={loading} className="w-full justify-center">
                        {loading ? "Verifying..." : "Login"}
                    </Button>
                </form>

                {error && <p className="text-red-400 text-sm mt-4">{error}</p>}

                <p className="text-xs text-gray-400 mt-5">
                    Don&apos;t have a key? <Link to="/" className="text-neon-cyan hover:underline">Create organization first</Link>.
                </p>
            </Card>
        </div>
    );
}
