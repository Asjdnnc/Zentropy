import { useState, useEffect, useCallback } from "react";
import {
  getTransactionHistory,
  getTransactionStatus,
  getActiveUserId,
  setActiveUserId,
  listWallets,
} from "../api/client";
import StatusBadge from "../components/StatusBadge";

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
      fetchHistory();
    } catch (err) {
      setStatusDetail({
        error: err.readableMessage || err.message || 'Failed to fetch transaction status'
      });
    }
  }

  const inputClass = "bg-[#111] border border-[#222] rounded-xl px-4 py-3 text-[13px] text-white placeholder-gray-600 focus:border-[#444] outline-none transition-all";

  return (
    <div className="space-y-8 animate-fade-in text-white font-sans max-w-7xl mx-auto w-full">
      <div className="flex flex-col md:flex-row justify-between items-end gap-6 mb-8 pl-1">
        <div>
          <h1 className="text-2xl font-bold tracking-tight mb-2">Ledger History</h1>
          <p className="text-gray-400 text-[14px]">
            Immutable record of quantum-secured operations
          </p>
        </div>
        <div className="text-right">
          <span className="text-white font-mono text-3xl font-bold tracking-tight block mb-1">
            {total}
          </span>
          <span className="text-gray-500 text-[11px] uppercase font-medium tracking-wider block">
            Total Transactions
          </span>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[20px] p-5 flex flex-wrap gap-4 items-center shadow-xl">
        <div className="min-w-[220px]">
          <select
            value={selectedUserId}
            onChange={(e) => {
              const value = e.target.value;
              setSelectedUserId(value);
              setActiveUserId(value);
              setPage(0);
            }}
            className={`${inputClass} appearance-none cursor-pointer w-full`}
          >
            <option value="" className="text-gray-500">Select Wallet...</option>
            {wallets.map((w) => (
              <option key={w.user_id} value={w.user_id}>
                {w.wallet_name || w.username || w.label || w.user_id}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1 min-w-[200px]">
          <input
            type="text"
            placeholder="Search by ID or address..."
            value={filter.label}
            onChange={(e) => {
              setFilter({ ...filter, label: e.target.value });
              setPage(0);
            }}
            className={`w-full ${inputClass}`}
          />
        </div>
        <div className="min-w-[160px]">
            <select
              value={filter.status}
              onChange={(e) => {
                setFilter({ ...filter, status: e.target.value });
                setPage(0);
              }}
              className={`${inputClass} appearance-none cursor-pointer w-full`}
            >
              <option value="">All Statuses</option>
              <option value="signed">Signed</option>
              <option value="proved">Proved</option>
              <option value="submitted">Submitted</option>
              <option value="confirmed">Confirmed</option>
              <option value="error">Error</option>
              <option value="proof_failed">Proof Failed</option>
            </select>
        </div>
        <button 
          onClick={fetchHistory} 
          className="px-5 py-3 bg-white text-black font-semibold rounded-xl text-[13px] hover:bg-gray-200 transition-colors"
        >
          Refresh
        </button>
      </div>

      {/* Transactions Table */}
      <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] overflow-hidden shadow-2xl">
        {loading ? (
          <div className="p-16 text-center flex flex-col items-center justify-center space-y-4">
            <svg className="animate-spin h-8 w-8 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
            <span className="text-gray-400 text-[13px] font-medium tracking-wide uppercase">Syncing Ledger...</span>
          </div>
        ) : filteredTransactions.length === 0 ? (
          <div className="p-16 text-center text-gray-500 text-[14px]">
            No transactions found matching criteria.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead className="bg-[#111] border-b border-[#1a1a1a]">
                <tr>
                  <th className="px-6 py-4 text-[11px] font-medium uppercase tracking-wider text-gray-500">TX ID</th>
                  <th className="px-6 py-4 text-[11px] font-medium uppercase tracking-wider text-gray-500">Wallet</th>
                  <th className="px-6 py-4 text-[11px] font-medium uppercase tracking-wider text-gray-500">Target</th>
                  <th className="px-6 py-4 text-[11px] font-medium uppercase tracking-wider text-gray-500">Amount</th>
                  <th className="px-6 py-4 text-[11px] font-medium uppercase tracking-wider text-gray-500">Status</th>
                  <th className="px-6 py-4 text-[11px] font-medium uppercase tracking-wider text-gray-500">Starknet Hash</th>
                  <th className="px-6 py-4 text-[11px] font-medium uppercase tracking-wider text-gray-500">Timestamp</th>
                  <th className="px-6 py-4 text-[11px] font-medium uppercase tracking-wider text-gray-500">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1a1a1a]">
                {filteredTransactions.map((tx) => (
                  <tr
                    key={tx.tx_id}
                    className="hover:bg-[#111]/50 transition-colors group"
                  >
                    <td className="px-6 py-4 font-mono text-[13px] text-white group-hover:text-blue-400 transition-colors">
                      {tx.tx_id.slice(0, 8)}...
                    </td>
                    <td className="px-6 py-4 text-[13px] text-gray-300">
                      {tx.account_id ? tx.account_id.slice(0, 8) + "..." : "-"}
                    </td>
                    <td className="px-6 py-4 font-mono text-[13px] text-gray-400">
                      {tx.type === "receive" 
                        ? (tx.sender_account_address ? "From: " + tx.sender_account_address.slice(0, 8) + "..." : "From: -")
                        : (tx.to_address ? "To: " + tx.to_address.slice(0, 8) + "..." : "To: -")}
                    </td>
                    <td className="px-6 py-4 font-mono text-[13px] font-medium">
                      <span className={tx.type === "receive" ? "text-green-400 bg-green-500/10 px-2 py-1 rounded" : "text-white bg-[#111] px-2 py-1 rounded border border-[#222]"}>
                        {tx.type === "receive" ? "+" : "-"}{tx.amount_strk || "0.000000"}
                      </span>
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
                          className="font-mono text-[13px] text-blue-400 hover:text-white transition-colors cursor-help bg-blue-500/10 px-2 py-1 rounded border border-blue-500/20"
                          title={tx.tx_hash}
                        >
                          {tx.tx_hash.slice(0, 8)}...
                        </span>
                      ) : (
                        <span className="text-gray-600 font-mono text-[13px]">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-gray-500 text-[12px]">
                      {formatTime(tx.created_at)}
                    </td>
                    <td className="px-6 py-4">
                      <button
                        onClick={() => handleCheckStatus(tx.tx_id)}
                        className="text-[11px] font-semibold text-gray-300 bg-[#111] border border-[#222] px-3 py-1.5 rounded-md hover:bg-white hover:text-black transition-colors uppercase tracking-wide"
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
      </div>

      {/* Pagination */}
      {total > limit && (
        <div className="flex justify-center items-center gap-6 mt-8">
          <button
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            className="px-4 py-2 bg-[#111] border border-[#222] text-white rounded-xl text-[13px] font-medium hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <span className="text-gray-500 text-[12px] font-medium uppercase tracking-wider">
            Page {page + 1} of {Math.ceil(total / limit)} {filteredTotal !== total ? `(Filtered ${filteredTotal})` : ""}
          </span>
          <button
            disabled={(page + 1) * limit >= total}
            onClick={() => setPage((p) => p + 1)}
            className="px-4 py-2 bg-[#111] border border-[#222] text-white rounded-xl text-[13px] font-medium hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}

      {/* Status Detail Modal */}
      {selectedTx && statusDetail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-2xl bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] shadow-2xl relative overflow-hidden flex flex-col max-h-[90vh]">
            <div className="flex items-center justify-between p-6 border-b border-[#1a1a1a] bg-[#050505]">
              <h3 className="text-lg font-bold text-white flex items-center gap-3 tracking-tight">
                TX Detail
                <span className="text-gray-500 text-[13px] font-mono font-normal">
                  {selectedTx}
                </span>
              </h3>
              <button
                onClick={() => {
                  setSelectedTx(null);
                  setStatusDetail(null);
                }}
                className="text-gray-500 hover:text-white transition-colors p-1"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-6">
                {statusDetail.error ? (
                <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-5">
                    <p className="text-red-400 text-[13px] font-mono">
                    {statusDetail.error}
                    </p>
                </div>
                ) : (
                <div className="space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="p-4 bg-[#111] rounded-xl border border-[#222]">
                        <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider block mb-2">
                        Status
                        </span>
                        <StatusBadge
                        status={STATUS_MAP[statusDetail.status] || "offline"}
                        label={statusDetail.status}
                        />
                    </div>
                    <div className="p-4 bg-[#111] rounded-xl border border-[#222]">
                        <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider block mb-2">
                        ZK Proof
                        </span>
                        <span
                        className={`font-semibold text-[13px] ${statusDetail.proof_valid ? "text-green-400" : "text-red-400"}`}
                        >
                        {statusDetail.proof_valid
                            ? "Verified Valid"
                            : "Not Verified"}
                        </span>
                    </div>
                    </div>

                    {statusDetail.proof_commitment && (
                    <div className="p-4 bg-[#111] rounded-xl border border-[#222]">
                        <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider block mb-2">
                        Proof Commitment
                        </span>
                        <p className="text-white font-mono text-[13px] break-all">
                        {statusDetail.proof_commitment}
                        </p>
                    </div>
                    )}

                    {statusDetail.tx_hash && (
                    <div className="p-4 bg-blue-500/5 rounded-xl border border-blue-500/20">
                        <span className="text-blue-400/70 text-[11px] font-medium uppercase tracking-wider block mb-2">
                        Starknet TX Hash
                        </span>
                        <p className="text-blue-400 font-mono text-[13px] break-all">
                        {statusDetail.tx_hash}
                        </p>
                    </div>
                    )}

                    <div className="grid grid-cols-2 gap-4">
                    <div className="p-4 bg-[#111] rounded-xl border border-[#222]">
                        <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider block mb-1">
                        Chain Status
                        </span>
                        <span className="text-white font-mono text-[13px]">
                        {statusDetail.starknet_status || "—"}
                        </span>
                    </div>
                    <div className="p-4 bg-[#111] rounded-xl border border-[#222]">
                        <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider block mb-1">
                        Last Updated
                        </span>
                        <span className="text-gray-300 text-[13px]">
                        {formatTime(statusDetail.confirmed_at || statusDetail.created_at)}
                        </span>
                    </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="p-4 bg-[#111] rounded-xl border border-[#222]">
                        <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider block mb-2">
                        Sender Account
                        </span>
                        <p className="text-gray-300 font-mono text-[13px] break-all">
                        {statusDetail.sender_account_address || "—"}
                        </p>
                    </div>
                    <div className="p-4 bg-[#111] rounded-xl border border-[#222]">
                        <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider block mb-2">
                        {statusDetail.submission_mode === "relayer" ? "Relayer" : "Submitted By"}
                        </span>
                        <p className="text-gray-300 font-mono text-[13px] break-all">
                        {statusDetail.submitted_by_address || "—"}
                        </p>
                        <p className="text-gray-500 text-[11px] mt-2 font-medium tracking-wider uppercase">
                        MODE: {statusDetail.submission_mode || "relayer"}
                        </p>
                    </div>
                    </div>

                    <div className="p-4 bg-[#111] rounded-xl border border-[#222]">
                    <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider block mb-2">
                        Prover Backend
                    </span>
                    <p className="text-white font-mono text-[13px] break-all">
                        {statusDetail.prover_backend || "unknown"}
                    </p>
                    {statusDetail.prover_fallback_reason && (
                        <p className="text-yellow-500 font-mono text-[12px] mt-2 bg-yellow-500/10 px-3 py-1.5 rounded-md border border-yellow-500/20">
                        Fallback: {statusDetail.prover_fallback_reason}
                        </p>
                    )}
                    </div>

                    {statusDetail.starknet_receipt && (
                    <div>
                        <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider block mb-2">
                        Receipt Data
                        </span>
                        <pre className="text-gray-400 text-[12px] font-mono bg-[#111] rounded-xl p-4 overflow-auto max-h-40 border border-[#222] scrollbar-thin scrollbar-thumb-[#333]">
                        {statusDetail.starknet_receipt}
                        </pre>
                    </div>
                    )}
                </div>
                )}
            </div>

            <div className="p-6 border-t border-[#1a1a1a] bg-[#050505] flex justify-end">
              <button
                onClick={() => {
                    setSelectedTx(null);
                    setStatusDetail(null);
                }}
                className="px-6 py-2.5 bg-white text-black font-semibold rounded-xl text-[13px] hover:bg-gray-200 transition-colors"
                >
                Close Details
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
