import { useState, useEffect } from "react";
import {
  getHealth,
  listWallets,
  getWalletBalance,
  getContractStatus,
  getTransactionHistory,
  getWalletInfo,
  getActiveUserId,
  setActiveUserId,
} from "../api/client";
import StatusBadge from "../components/StatusBadge";
import Card from "../components/Card";
import WalletCard from "../components/WalletCard";
import { Link } from "react-router-dom";

export default function Dashboard() {
  const [health, setHealth] = useState(null);
  const [wallets, setWallets] = useState([]);
  const [balances, setBalances] = useState({});
  const [contract, setContract] = useState(null);
  const [txCount, setTxCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchAll() {
      try {
        const [healthRes, walletsRes] = await Promise.all([
          getHealth().catch(() => null),
          listWallets().catch(() => null),
        ]);
        if (healthRes) setHealth(healthRes.data);
        const users = walletsRes?.data?.users || walletsRes?.data?.wallets || [];
        const walletList = await Promise.all(
          users.map(async (u) => {
            const userId = u.user_id || u.label;
            if (!userId) return null;
            try {
              const walletRes = await getWalletInfo(userId);
              return {
                label: userId,
                user_id: userId,
                username: u.username || u.email || userId,
                ...walletRes.data,
              };
            } catch {
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
        const normalizedWallets = walletList.filter(Boolean);
        setWallets(normalizedWallets);

        const persistedUserId = getActiveUserId();
        const defaultUserId = persistedUserId || normalizedWallets[0]?.user_id;
        if (!persistedUserId && defaultUserId) {
          setActiveUserId(defaultUserId);
        }

        const [contractRes, txRes] = await Promise.all([
          getContractStatus().catch(() => null),
          defaultUserId
            ? getTransactionHistory({ user_id: defaultUserId, limit: 1 }).catch(() => null)
            : Promise.resolve(null),
        ]);
        if (contractRes) setContract(contractRes.data);
        if (txRes) setTxCount(txRes.data.total || 0);

        // Fetch balances for deployed wallets
        const deployed = normalizedWallets.filter(
          (w) => w.contract_address && w.deployment_status === "deployed"
        );
        const balanceResults = await Promise.all(
          deployed.map((w) =>
            getWalletBalance(w.user_id)
              .then((r) => ({ user_id: w.user_id, data: r.data }))
              .catch(() => null)
          )
        );
        const b = {};
        balanceResults.forEach((r) => {
          if (r) b[r.user_id] = r.data;
        });
        setBalances(b);
      } catch (err) {
        console.error("Dashboard fetch error:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchAll();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-100px)]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-neon-cyan border-t-transparent rounded-full animate-spin"></div>
          <div className="text-neon-cyan font-orbitron animate-pulse">
            INITIALIZING QUANTUM INTERFACE...
          </div>
        </div>
      </div>
    );
  }

  const deployedCount = wallets.filter(
    (w) => w.deployment_status === "deployed"
  ).length;

  // Calculate total portfolio balance
  const totalBalance = Object.values(balances).reduce((sum, b) => {
    const val = parseFloat(b?.balance_display || b?.balance_strk || "0");
    return sum + (isNaN(val) ? 0 : val);
  }, 0);

  const stats = [
    {
      label: "API Status",
      value: health ? "ONLINE" : "OFFLINE",
      sub: health ? `v${health.version}` : "reconnecting...",
      status: health ? "healthy" : "offline",
      color: "neon-cyan",
    },
    {
      label: "Deployed Wallets",
      value: `${deployedCount}/${wallets.length}`,
      sub: "QuantumGuard Contracts",
      status: deployedCount > 0 ? "ready" : "default",
      color: "neon-purple",
    },
    {
      label: "Portfolio",
      value: `${totalBalance.toFixed(4)}`,
      sub: "Total STRK Balance",
      status: totalBalance > 0 ? "ready" : "default",
      color: "neon-green",
    },
    {
      label: "Starknet Bridge",
      value: contract?.deployed ? "ACTIVE" : deployedCount > 0 ? "ACTIVE" : "PENDING",
      sub: deployedCount > 0 ? "Sepolia Testnet" : "Not Deployed",
      status: deployedCount > 0 ? "ready" : "pending",
      color: "white",
    },
  ];

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat, index) => (
          <Card
            key={index}
            variant="default"
            className="relative overflow-hidden group"
          >
            <div
              className={`absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity text-${stat.color}`}
            >
              <svg
                className="w-16 h-16"
                fill="currentColor"
                viewBox="0 0 24 24"
              >
                <path d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div className="flex flex-col gap-2 relative z-10">
              <div className="flex justify-between items-start">
                <span className="text-gray-400 text-xs font-orbitron tracking-wider uppercase">
                  {stat.label}
                </span>
                <StatusBadge status={stat.status} />
              </div>
              <span
                className={`text-3xl font-bold font-orbitron text-${stat.color === "white" ? "white" : stat.color} drop-shadow-[0_0_10px_rgba(255,255,255,0.1)]`}
              >
                {stat.value}
              </span>
              <span className="text-xs text-gray-500 font-mono">
                {stat.sub}
              </span>
            </div>
          </Card>
        ))}
      </div>

      {/* Architecture Section */}
      <Card variant="purple" title="SYSTEM ARCHITECTURE" className="relative">
        <div className="absolute inset-0 bg-gradient-to-r from-neon-purple/5 to-transparent rounded-xl pointer-events-none"></div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 relative z-10">
          {[
            { title: "PQC Backend", desc: "ML-DSA-44 Signatures", step: "01" },
            { title: "Rust Prover", desc: "ZK-STARK Logic", step: "02" },
            {
              title: "Cairo Contract",
              desc: "Account Abstraction",
              step: "03",
            },
            { title: "User Interface", desc: "Visualization", step: "04" },
          ].map((item, i) => (
            <div
              key={i}
              className="bg-black/20 border border-white/5 p-4 rounded-lg relative overflow-hidden group hover:border-neon-purple/50 transition-colors"
            >
              <div className="absolute -right-4 -bottom-4 text-6xl font-bold text-white/5 group-hover:text-neon-purple/10 transition-colors font-orbitron">
                {item.step}
              </div>
              <h4 className="text-neon-cyan font-orbitron text-sm mb-1">
                {item.title}
              </h4>
              <p className="text-gray-400 text-xs">{item.desc}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* Wallets Overview */}
      {wallets.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-orbitron text-white">YOUR WALLETS</h2>
            <Link
              to="/wallet"
              className="text-xs text-neon-cyan hover:underline font-orbitron"
            >
              + New Wallet
            </Link>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {wallets.map((w) => (
              <WalletCard
                key={w.user_id}
                wallet={w}
                balance={balances[w.user_id]}
              />
            ))}
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card title="Quick Actions">
          <div className="grid grid-cols-2 gap-4">
            <Link
              to="/wallet"
              className="p-4 bg-white/5 border border-white/10 rounded-lg hover:bg-neon-cyan/10 hover:border-neon-cyan/50 hover:text-neon-cyan transition-all flex flex-col items-center gap-2 group text-center"
            >
              <svg
                className="w-6 h-6 text-gray-400 group-hover:text-neon-cyan transition-colors"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
              <span className="text-sm font-medium">Create Wallet</span>
            </Link>
            <Link
              to="/send"
              className="p-4 bg-white/5 border border-white/10 rounded-lg hover:bg-neon-purple/10 hover:border-neon-purple/50 hover:text-neon-purple transition-all flex flex-col items-center gap-2 group text-center"
            >
              <svg
                className="w-6 h-6 text-gray-400 group-hover:text-neon-purple transition-colors"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
              <span className="text-sm font-medium">Send STRK</span>
            </Link>
            <Link
              to="/receive"
              className="p-4 bg-white/5 border border-white/10 rounded-lg hover:bg-neon-green/10 hover:border-neon-green/50 hover:text-neon-green transition-all flex flex-col items-center gap-2 group text-center"
            >
              <svg
                className="w-6 h-6 text-gray-400 group-hover:text-neon-green transition-colors"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                />
              </svg>
              <span className="text-sm font-medium">Receive</span>
            </Link>
            <Link
              to="/history"
              className="p-4 bg-white/5 border border-white/10 rounded-lg hover:bg-white/10 hover:border-white/30 transition-all flex flex-col items-center gap-2 group text-center"
            >
              <svg
                className="w-6 h-6 text-gray-400 group-hover:text-white transition-colors"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span className="text-sm font-medium">History</span>
            </Link>
          </div>
        </Card>

        <Card title="Latest Activity">
          <div className="text-center py-8 text-gray-500 text-sm">
            {txCount > 0 ? (
              <Link to="/history" className="text-neon-cyan hover:underline">
                View recent transactions
              </Link>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <span className="opacity-50">
                  No recent activity detected on the quantum field.
                </span>
                <Link
                  to="/wallet"
                  className="text-neon-cyan hover:underline text-xs"
                >
                  Initialize a wallet to begin.
                </Link>
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
