import { useState, useEffect } from "react";
import {
  signTransaction,
  executeTransaction,
  listWallets,
} from "../api/client";
import StatusBadge from "../components/StatusBadge";
import Card from "../components/Card";
import Button from "../components/Button";

export default function Transactions() {
  const [wallets, setWallets] = useState([]);
  const [form, setForm] = useState({
    to: "",
    amount: "",
    nonce: "0",
    data: "",
    user_id: "",
  });
  const [mode, setMode] = useState("sign"); // 'sign' or 'execute'
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    listWallets()
      .then((res) => {
        const users = res.data.users || res.data.wallets || [];
        setWallets(users);
        if (users.length > 0) {
          setForm((prev) => ({ ...prev, user_id: prev.user_id || users[0].user_id || users[0].label || "" }));
        }
      })
      .catch(() => { });
  }, []);

  function handleChange(e) {
    setForm({ ...form, [e.target.name]: e.target.value });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    const payload = {
      user_id: form.user_id,
      to_address: form.to,
      amount_strk: parseFloat(form.amount),
    };

    try {
      const res = mode === "execute"
        ? await executeTransaction(payload)
        : await signTransaction(payload);
      setResult({ mode, ...res.data });
    } catch (err) {
      setError(
        err.readableMessage ||
        err.response?.data?.detail ||
        err.message ||
        "Transaction failed",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Transactions</h1>
        <p className="text-gray-400 mt-1">
          Sign and execute quantum-resistant transactions
        </p>
      </div>

      {/* Mode Toggle */}
      <div className="flex gap-2">
        <button
          onClick={() => setMode("sign")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${mode === "sign"
            ? "bg-indigo-600 text-white"
            : "bg-gray-800 text-gray-400 hover:text-white"
            }`}
        >
          Sign Only
        </button>
        <button
          onClick={() => setMode("execute")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${mode === "execute"
            ? "bg-indigo-600 text-white"
            : "bg-gray-800 text-gray-400 hover:text-white"
            }`}
        >
          Sign + Prove + Execute
        </button>
      </div>

      {/* Transaction Form */}
      <div className="bg-gray-800 border border-gray-700 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white mb-4">
          {mode === "execute" ? "Execute Transaction" : "Sign Transaction"}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Wallet selector */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">Wallet</label>
            <select
              name="user_id"
              value={form.user_id}
              onChange={handleChange}
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-indigo-500"
            >
              {wallets.length === 0 ? (
                <option value="">No wallet</option>
              ) : (
                wallets.map((w) => (
                  <option key={w.user_id || w.label} value={w.user_id || w.label}>
                    {w.username || w.email || w.user_id || w.label}
                  </option>
                ))
              )}
            </select>
          </div>

          {/* To address */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Recipient Address
            </label>
            <input
              type="text"
              name="to"
              value={form.to}
              onChange={handleChange}
              placeholder="0x..."
              required
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 font-mono focus:outline-none focus:border-indigo-500"
            />
          </div>

          {/* Amount */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Amount</label>
              <input
                type="number"
                name="amount"
                value={form.amount}
                onChange={handleChange}
                placeholder="0.0"
                step="0.001"
                required
                className="w-full bg-gray-900 border border-gray-600 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Nonce</label>
              <input
                type="number"
                name="nonce"
                value={form.nonce}
                onChange={handleChange}
                min="0"
                className="w-full bg-gray-900 border border-gray-600 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
              />
            </div>
          </div>

          {/* Optional data */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Calldata (optional)
            </label>
            <input
              type="text"
              name="data"
              value={form.data}
              onChange={handleChange}
              placeholder="Optional hex calldata"
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full px-6 py-3 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading
              ? "Processing..."
              : mode === "execute"
                ? "Sign + Prove + Execute"
                : "Sign Transaction"}
          </button>
        </form>
      </div>

      {/* Result */}
      {result && (
        <div className="bg-gray-800 border border-green-500/30 rounded-xl p-6 space-y-4">
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-semibold text-white">
              Transaction Result
            </h3>
            <StatusBadge
              status={
                result.status === "signed" || result.status === "executed"
                  ? "ready"
                  : "warning"
              }
              label={result.status}
            />
          </div>

          {result.tx_id && (
            <div>
              <span className="text-gray-500 text-sm">Transaction ID</span>
              <p className="text-indigo-400 font-mono text-xs">
                {result.tx_id}
              </p>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            {result.signature_size && (
              <div>
                <span className="text-gray-500">Signature Size</span>
                <p className="text-white">{result.signature_size} bytes</p>
              </div>
            )}
            {result.message_hash && (
              <div>
                <span className="text-gray-500">Message Hash</span>
                <p className="text-white font-mono text-xs">
                  {result.message_hash.slice(0, 32)}...
                </p>
              </div>
            )}
            {result.pubkey_hash && (
              <div>
                <span className="text-gray-500">Identity Hash</span>
                <p className="text-white font-mono text-xs">
                  {result.pubkey_hash.slice(0, 32)}...
                </p>
              </div>
            )}
            {result.proof_commitment && (
              <div>
                <span className="text-gray-500">Proof Commitment</span>
                <p className="text-white font-mono text-xs">
                  {result.proof_commitment.slice(0, 32)}...
                </p>
              </div>
            )}
            {result.proof_valid !== undefined && (
              <div>
                <span className="text-gray-500">Proof Valid</span>
                <p className="text-white">
                  {result.proof_valid ? "✓ Yes" : "✗ No"}
                </p>
              </div>
            )}
            {result.starknet_status && (
              <div>
                <span className="text-gray-500">Starknet Status</span>
                <p className="text-yellow-400">{result.starknet_status}</p>
              </div>
            )}
            {result.starknet_tx_hash && (
              <div className="md:col-span-2">
                <span className="text-gray-500">Starknet TX Hash</span>
                <p className="text-blue-400 font-mono text-xs break-all">
                  {result.starknet_tx_hash}
                </p>
              </div>
            )}
          </div>

          {result.note && (
            <p className="text-gray-400 text-sm bg-gray-900 rounded-lg p-3">
              {result.note}
            </p>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-5">
          <p className="text-red-400">{error}</p>
        </div>
      )}
    </div>
  );
}
