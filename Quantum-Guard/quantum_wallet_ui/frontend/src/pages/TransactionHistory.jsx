import { useState, useEffect, useCallback } from "react";
import {
  getTransactionHistory,
  getTransactionStatus,
  getActiveUserId,
  setActiveUserId,
  listWallets,
} from "../api/client";
import StatusBadge from "../components/StatusBadge";
import Card from "../components/Card";
import Button from "../components/Button";

const STATUS_MAP = {
  signed: "pending",
  proved: "pending",
  submitted: "pending",
  confirmed: "ready",
  executed: "ready",
  failed: "error",
  proof_failed: "error",
  submission_failed: "error",
  rejected: "error",
  error: "error",
};

function formatTime(timestamp) {
  if (!timestamp) return "—";
  const numeric = Number(timestamp);
  const d = Number.isFinite(numeric)
    ? new Date((numeric > 1e12 ? numeric : numeric * 1000))
    : new Date(timestamp);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

export default function TransactionHistory() {
  const [transactions, setTransactions] = useState([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState({ label: "", status: "" });
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedTx, setSelectedTx] = useState(null);
  const [statusDetail, setStatusDetail] = useState(null);
  const [wallets, setWallets] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState(getActiveUserId());
  const limit = 20;

  const filteredTransactions = transactions.filter((tx) => {
    if (filter.status) {
      const txStatus = String(tx.status || "").toLowerCase();
      const wanted = String(filter.status || "").toLowerCase();
      if (txStatus !== wanted) return false;
    }

    if (filter.label) {
      const target = `${tx.account_id || ""} ${tx.tx_id || ""} ${tx.to_address || ""}`.toLowerCase();
      if (!target.includes(filter.label.toLowerCase())) return false;
    }

    return true;
  });

  const filteredTotal = filteredTransactions.length;

  const fetchWalletList = useCallback(async () => {
    try {
      const res = await listWallets(200, 0);
      const users = res.data.users || [];
      setWallets(users);

      if (!selectedUserId && users.length > 0) {
        const first = users[0].user_id;
        setSelectedUserId(first);
        setActiveUserId(first);
      }
    } catch {
      setWallets([]);
    }
  }, [selectedUserId]);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      if (!selectedUserId) {
        setTransactions([]);
        setTotal(0);
        return;
      }
      const params = { limit, offset: page * limit };
      // Backend endpoint only supports: user_id, limit, offset
      // Note: label and status filtering needs to be done on the frontend
      const res = await getTransactionHistory({ ...params, user_id: selectedUserId });
      setTransactions(res.data.transactions || []);
      setTotal(res.data.total || 0);
    } catch {
      setTransactions([]);
    } finally {
      setLoading(false);
    }
  }, [page, selectedUserId]);

  useEffect(() => {
    fetchWalletList();
  }, [fetchWalletList]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  async function handleCheckStatus(txId) {
    try {
      const res = await getTransactionStatus(txId);
      setStatusDetail(res.data);
      setSelectedTx(txId);
      // Refresh to pick up any state changes
      fetchHistory();
    } catch (err) {
      setStatusDetail({
        error: err.readableMessage || err.message || 'Failed to fetch transaction status'
      });
    }
  }

  const inputClass =
    "bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 text-sm focus:outline-none focus:border-neon-cyan/50 focus:shadow-[0_0_10px_rgba(0,243,255,0.1)] transition-all";

  return (
    <div className="space-y-8 animate-fade-in">
      <div className="flex flex-col md:flex-row justify-between items-end gap-4">
        <div>
          <h1 className="text-3xl font-bold font-orbitron text-white">
            Ledger History
          </h1>
          <p className="text-gray-400 mt-1">
            Immutable record of quantum-secured operations
          </p>
        </div>
        <div className="text-right">
          <span className="text-neon-cyan font-mono text-2xl font-bold">
            {total}
          </span>
          <span className="text-gray-500 text-xs uppercase tracking-wider block">
            Total Transactions
          </span>
        </div>
      </div>

      {/* Filters */}
      <Card className="flex flex-wrap gap-3 items-center p-4">
        <div className="min-w-[220px]">
          <select
            value={selectedUserId}
            onChange={(e) => {
              const value = e.target.value;
              setSelectedUserId(value);
              setActiveUserId(value);
              setPage(0);
            }}
            className={`${inputClass} appearance-none cursor-pointer`}
          >
            <option value="">Select Wallet</option>
            {wallets.map((w) => (
              <option key={w.user_id} value={w.user_id}>
                {w.username || w.email || w.user_id}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1 min-w-[200px]">
          <input
            type="text"
            placeholder="Filter by wallet label..."
            value={filter.label}
            onChange={(e) => {
              setFilter({ ...filter, label: e.target.value });
              setPage(0);
            }}
            className={`w-full ${inputClass}`}
          />
        </div>
        <select
          value={filter.status}
          onChange={(e) => {
            setFilter({ ...filter, status: e.target.value });
            setPage(0);
          }}
          className={`${inputClass} appearance-none cursor-pointer`}
        >
          <option value="">All Statuses</option>
          <option value="signed">Signed</option>
          <option value="proved">Proved</option>
          <option value="submitted">Submitted</option>
          <option value="confirmed">Confirmed</option>
          <option value="error">Error</option>
          <option value="proof_failed">Proof Failed</option>
        </select>
        <Button onClick={fetchHistory} variant="secondary" className="h-[38px]">
          Refresh
        </Button>
      </Card>

      {/* Transactions Table */}
      <Card className="overflow-hidden p-0" variant="default">
        {loading ? (
          <div className="p-12 text-center">
            <div className="w-12 h-12 border-4 border-neon-cyan border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
            <div className="text-neon-cyan font-orbitron animate-pulse">
              SYNCING LEDGER...
            </div>
          </div>
        ) : filteredTransactions.length === 0 ? (
          <div className="p-12 text-center text-gray-500 italic">
            No transactions found matching criteria.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-gray-400 uppercase bg-black/40 font-orbitron tracking-wider">
                <tr>
                  <th className="px-6 py-4">TX ID</th>
                  <th className="px-6 py-4">Wallet</th>
                  <th className="px-6 py-4">Target</th>
                  <th className="px-6 py-4">Amount</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4">Starknet Hash</th>
                  <th className="px-6 py-4">Timestamp</th>
                  <th className="px-6 py-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {filteredTransactions.map((tx) => (
                  <tr
                    key={tx.tx_id}
                    className="hover:bg-white/5 transition-colors group"
                  >
                    <td className="px-6 py-4 font-mono text-xs text-neon-purple/80 group-hover:text-neon-purple transition-colors">
                      {tx.tx_id.slice(0, 8)}...
                    </td>
                    <td className="px-6 py-4 text-gray-300">
                      {tx.account_id ? tx.account_id.slice(0, 8) + "..." : "-"}
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-gray-400">
                      {tx.to_address ? tx.to_address.slice(0, 10) + "..." : "-"}
                    </td>
                    <td className="px-6 py-4 text-white font-medium">
                      {tx.amount_strk || "0.000000"}
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge
                        status={STATUS_MAP[tx.status] || "offline"}
                        label={tx.status}
                      />
                    </td>
                    <td className="px-6 py-4">
                      {tx.tx_hash ? (
                        <span
                          className="font-mono text-xs text-blue-400 hover:text-blue-300 cursor-help"
                          title={tx.tx_hash}
                        >
                          {tx.tx_hash.slice(0, 10)}...
                        </span>
                      ) : (
                        <span className="text-gray-600 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-gray-400 text-xs">
                      {formatTime(tx.created_at)}
                    </td>
                    <td className="px-6 py-4">
                      <button
                        onClick={() => handleCheckStatus(tx.tx_id)}
                        className="text-xs text-neon-cyan border border-neon-cyan/30 px-2 py-1 rounded hover:bg-neon-cyan/10 hover:shadow-[0_0_10px_rgba(0,243,255,0.2)] transition-all uppercase font-bold tracking-wide"
                      >
                        Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Pagination */}
      {total > limit && (
        <div className="flex justify-center gap-4">
          <Button
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            variant="secondary"
          >
            Previous
          </Button>
          <span className="text-gray-400 text-sm self-center font-orbitron">
            PAGE {page + 1} OF {Math.ceil(total / limit)} {filteredTotal !== total ? `(filtered ${filteredTotal})` : ""}
          </span>
          <Button
            disabled={(page + 1) * limit >= total}
            onClick={() => setPage((p) => p + 1)}
            variant="secondary"
          >
            Next
          </Button>
        </div>
      )}

      {/* Status Detail Modal */}
      {selectedTx && statusDetail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <Card
            variant="neon"
            className="w-full max-w-2xl max-h-[90vh] overflow-y-auto relative shadow-2xl"
          >
            <div className="flex items-center justify-between mb-6 border-b border-white/10 pb-4">
              <h3 className="text-lg font-orbitron font-bold text-white flex items-center gap-2">
                <span className="text-neon-cyan">TX DETAIL</span>
                <span className="text-gray-500 text-sm font-mono">
                  {selectedTx}
                </span>
              </h3>
              <button
                onClick={() => {
                  setSelectedTx(null);
                  setStatusDetail(null);
                }}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <svg
                  className="w-6 h-6"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>

            {statusDetail.error ? (
              <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-5 mb-4">
                <p className="text-red-400 text-sm font-mono">
                  {statusDetail.error}
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 bg-white/5 rounded-lg border border-white/5">
                    <span className="text-gray-500 text-xs uppercase tracking-wider block mb-1">
                      Status
                    </span>
                    <StatusBadge
                      status={STATUS_MAP[statusDetail.status] || "offline"}
                      label={statusDetail.status}
                    />
                  </div>
                  <div className="p-4 bg-white/5 rounded-lg border border-white/5">
                    <span className="text-gray-500 text-xs uppercase tracking-wider block mb-1">
                      ZK Proof
                    </span>
                    <span
                      className={`font-bold ${statusDetail.proof_valid ? "text-neon-green" : "text-red-400"}`}
                    >
                      {statusDetail.proof_valid
                        ? "VERIFIED VALID"
                        : "NOT VERIFIED"}
                    </span>
                  </div>
                </div>

                {statusDetail.proof_commitment && (
                  <div className="p-4 bg-black/30 rounded-lg border border-white/5">
                    <span className="text-gray-500 text-xs uppercase tracking-wider block mb-2">
                      Proof Commitment
                    </span>
                    <p className="text-neon-purple font-mono text-xs break-all leading-relaxed">
                      {statusDetail.proof_commitment}
                    </p>
                  </div>
                )}

                {statusDetail.tx_hash && (
                  <div className="p-4 bg-indigo-900/10 rounded-lg border border-indigo-500/20">
                    <span className="text-gray-500 text-xs uppercase tracking-wider block mb-2">
                      Starknet TX Hash
                    </span>
                    <p className="text-indigo-300 font-mono text-xs break-all">
                      {statusDetail.tx_hash}
                    </p>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-white/5 rounded-lg">
                    <span className="text-gray-500 text-xs uppercase tracking-wider block mb-1">
                      Chain Status
                    </span>
                    <span className="text-white font-mono text-sm">
                      {statusDetail.starknet_status || "—"}
                    </span>
                  </div>
                  <div className="p-4 bg-white/5 rounded-lg">
                    <span className="text-gray-500 text-xs uppercase tracking-wider block mb-1">
                      Last Updated
                    </span>
                    <span className="text-white text-sm">
                      {formatTime(statusDetail.confirmed_at || statusDetail.created_at)}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 bg-white/5 rounded-lg border border-white/5">
                    <span className="text-gray-500 text-xs uppercase tracking-wider block mb-2">
                      Sender Account
                    </span>
                    <p className="text-gray-300 font-mono text-xs break-all">
                      {statusDetail.sender_account_address || "—"}
                    </p>
                  </div>
                  <div className="p-4 bg-white/5 rounded-lg border border-white/5">
                    <span className="text-gray-500 text-xs uppercase tracking-wider block mb-2">
                      {statusDetail.submission_mode === "relayer" ? "Relayer" : "Submitted By"}
                    </span>
                    <p className="text-gray-300 font-mono text-xs break-all">
                      {statusDetail.submitted_by_address || "—"}
                    </p>
                    <p className="text-gray-500 text-[11px] mt-2 uppercase tracking-wider">
                      Mode: {statusDetail.submission_mode || "relayer"}
                    </p>
                  </div>
                </div>

                <div className="p-4 bg-white/5 rounded-lg border border-white/5">
                  <span className="text-gray-500 text-xs uppercase tracking-wider block mb-2">
                    Prover Backend
                  </span>
                  <p className="text-neon-cyan font-mono text-xs break-all">
                    {statusDetail.prover_backend || "unknown"}
                  </p>
                  {statusDetail.prover_fallback_reason && (
                    <p className="text-yellow-300 font-mono text-[11px] mt-2 break-all">
                      fallback: {statusDetail.prover_fallback_reason}
                    </p>
                  )}
                </div>

                {statusDetail.starknet_receipt && (
                  <div>
                    <span className="text-gray-500 text-xs uppercase tracking-wider block mb-2">
                      Receipt Data
                    </span>
                    <pre className="text-gray-400 text-xs font-mono bg-black/50 p-4 rounded-lg overflow-auto max-h-40 border border-white/5">
                      {statusDetail.starknet_receipt}
                    </pre>
                  </div>
                )}
              </div>
            )}

            <div className="mt-6 flex justify-end">
              <Button onClick={() => setSelectedTx(null)} variant="secondary">
                Close Details
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
