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
import { Link } from "react-router-dom";

function formatTime(timestamp) {
  if (!timestamp) return "—";
  const numeric = Number(timestamp);
  const d = Number.isFinite(numeric)
    ? new Date((numeric > 1e12 ? numeric : numeric * 1000))
    : new Date(timestamp);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

export default function Dashboard() {
  const [health, setHealth] = useState(null);
  const [wallets, setWallets] = useState([]);
  const [balances, setBalances] = useState({});
  const [contract, setContract] = useState(null);
  const [txCount, setTxCount] = useState(0);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [strkPrice, setStrkPrice] = useState(0.40); // default
  const [showBalance, setShowBalance] = useState(true);
  const [activeTab, setActiveTab] = useState('Tokens');
  const [txWalletId, setTxWalletId] = useState("");
  const [selectedWallet, setSelectedWallet] = useState(null);

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
        
        if (defaultUserId) {
            setTxWalletId(defaultUserId);
        }

        const contractRes = await getContractStatus().catch(() => null);
        if (contractRes) setContract(contractRes.data);

        // Fetch balances for all wallets
        const balanceResults = await Promise.all(
          normalizedWallets.map((w) =>
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

        // Fetch live STRK price
        try {
          const pRes = await fetch("https://api.coingecko.com/api/v3/simple/price?ids=starknet&vs_currencies=usd");
          const pData = await pRes.json();
          if (pData?.starknet?.usd) {
            setStrkPrice(pData.starknet.usd);
          }
        } catch (e) {
          console.warn("Could not fetch real STRK price, using fallback.");
        }
      } catch (err) {
        console.error("Dashboard fetch error:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchAll();
  }, []);

  // Dedicated effect for fetching transactions whenever txWalletId changes
  useEffect(() => {
    if (!txWalletId) return;
    
    let isCancelled = false;
    async function fetchTx() {
      try {
        const txRes = await getTransactionHistory({ user_id: txWalletId, limit: 15 });
        if (!isCancelled && txRes) {
          setTxCount(txRes.data.total || 0);
          setTransactions(txRes.data.transactions || []);
        }
      } catch (err) {
        if (!isCancelled) setTransactions([]);
      }
    }
    fetchTx();
    
    return () => { isCancelled = true; };
  }, [txWalletId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[500px]">
        <div className="text-gray-400 font-medium font-sans">Loading Dashboard...</div>
      </div>
    );
  }

  // Calculate total portfolio balance
  const totalBalance = Object.values(balances).reduce((sum, b) => {
    const val = parseFloat(b?.balance_display || b?.balance_strk || "0");
    return sum + (isNaN(val) ? 0 : val);
  }, 0);

  // Real fiat conversion based on fetched live price
  const totalFiat = totalBalance * strkPrice;

  return (
    <div className="bg-black text-white font-sans mg-0 w-full animate-fade-in">
      <div className="w-full">
        {/* Action Bar */}
        <div className="flex flex-wrap items-center justify-between gap-4 mb-4 overflow-x-auto pb-2 scrollbar-none">
          <div className="flex items-center gap-3">
            {['Send', 'Receive'].map((action) => (
              <Link key={action} to={action === 'Send' ? '/send' : action === 'Receive' ? '/receive' : action === 'Swap' ? '/swap' : action === 'Bridge' ? '/bridge' : action === 'Stake' ? '/stake' : '#'} className="px-[22px] py-[7px] bg-black text-white font-medium text-sm rounded-full border border-gray-700 flex items-center gap-2 hover:bg-[#121212] transition-colors whitespace-nowrap">
                {action === 'Send' && <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" /></svg>}
                {action === 'Receive' && <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" /></svg>}
                {action}
              </Link>
            ))}
          </div>  
          <Link to="/wallet" className="px-5 py-[7px] bg-transparent text-white font-medium text-sm rounded-full border border-gray-700 flex items-center gap-2 hover:bg-[#121212] transition-colors whitespace-nowrap ml-auto">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            Add an account
          </Link>
        </div>

        {/* Portfolio Center */}
        <div className="my-10 pl-2">
          <h2 className="text-[17px] font-semibold text-white mb-2">Decentralized accounts</h2>
          <div className="flex items-center gap-4">
            <span className="text-[44px] font-bold tracking-tight">
              {showBalance ? `$${totalFiat.toFixed(2)}` : '***'}
            </span>
            <button
              onClick={() => setShowBalance(!showBalance)}
              className="text-gray-500 hover:text-white transition-colors mt-2"
              title={showBalance ? "Hide Balance" : "Show Balance"}
            >
              {showBalance ? (
                <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" /></svg>
              ) : (
                <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
              )}
            </button>
          </div>
          <p className="text-sm text-red-500 mt-1 font-medium tracking-wide">
            {showBalance ? '-$0.00 (-0.00%)' : '***'}
          </p>
        </div>

        {/* Tabs Menu */}
        <div className="flex items-center justify-between border-b border-[#222] mb-5 px-4 h-12">
          <div className="flex items-center gap-10 h-full">
            <div 
              onClick={() => setActiveTab('Tokens')}
              className={`h-full flex items-center text-[15px] font-semibold cursor-pointer relative top-[1px] ${activeTab === 'Tokens' ? 'text-blue-500 border-b-[2px] border-blue-500' : 'text-gray-400 hover:text-gray-200 transition-colors border-b-[2px] border-transparent'}`}>
              Tokens
            </div>
            <div 
              onClick={() => setActiveTab('Transactions')}
              className={`h-full flex items-center text-[15px] font-semibold cursor-pointer relative top-[1px] ${activeTab === 'Transactions' ? 'text-blue-500 border-b-[2px] border-blue-500' : 'text-gray-400 hover:text-gray-200 transition-colors border-b-[2px] border-transparent'}`}>
              Transactions
            </div>
          </div>

          {/* Conditional Dropdown specifically for Transactions Tab */}
          {activeTab === 'Transactions' && wallets.length > 0 && (
            <div className="flex items-center gap-3 relative top-[-4px]">
              <span className="text-[12px] text-gray-500 font-medium uppercase tracking-wider hidden sm:inline-block">Filter Wallet</span>
              <div className="relative">
                <select 
                    value={txWalletId} 
                    onChange={(e) => {
                        setTxWalletId(e.target.value);
                    }}
                    className="appearance-none bg-[#111] border border-[#222] focus:border-[#444] rounded-lg pl-3 pr-8 py-1.5 text-[13px] text-white outline-none cursor-pointer transition-colors shadow-lg font-medium"
                >
                    {wallets.map(w => (
                        <option key={w.user_id} value={w.user_id}>
                            {w.wallet_name || w.username || w.label || w.user_id}
                        </option>
                    ))}
                </select>
                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2.5 text-gray-500">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Data Table */}
        <div className="w-full text-[15px] font-sans">
          
          {activeTab === 'Tokens' ? (
            <>
              {/* Tokens Header */}
              <div className="grid grid-cols-[3fr_1.5fr_1.5fr_1.5fr] gap-4 px-6 py-3 text-[#999] border-b border-[#222] mb-1">
                <div className="flex items-center gap-1 font-medium text-[13px] uppercase tracking-wider">Token <svg className="w-[14px] h-[14px]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg></div>
                <div className="text-blue-500 flex items-center gap-1 font-semibold text-[13px] uppercase tracking-wider">Portfolio % <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" /></svg></div>
                <div className="font-medium text-[13px] uppercase tracking-wider">Price (24hr)</div>
                <div className="text-right font-medium text-[13px] uppercase tracking-wider">Balance</div>
              </div>

              {/* Tokens Rows */}
              {wallets.length === 0 ? (
                 <div className="text-center py-10 text-gray-500">No active accounts found. Navigate to '+ Add an account' to deploy.</div>
              ) : (
                wallets.map((wallet, idx) => {
                  const balObj = balances[wallet.user_id];
                  const balStrk = parseFloat(balObj?.balance_display || balObj?.balance_strk || "0");
                  const totalStrkFloat = totalBalance > 0 ? totalBalance : 1;
                  const percentage = ((balStrk / totalStrkFloat) * 100).toFixed(2);
                  
                  return (
                    <div 
                      key={wallet.user_id} 
                      onClick={() => setSelectedWallet(wallet)}
                      className="grid grid-cols-[3fr_1.5fr_1.5fr_1.5fr] gap-4 px-6 py-[18px] hover:bg-[#111] rounded-[14px] transition-colors items-center cursor-pointer border-b border-transparent hover:border-transparent"
                    >
                      <div className="flex items-center gap-[18px]">
                        <div className="w-9 h-9 rounded-full bg-indigo-600 flex items-center justify-center relative flex-shrink-0 shadow-lg">
                           <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 12h14"></path><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 5l7 7-7 7"></path></svg>
                           <div className="absolute -top-1 -right-1 w-[18px] h-[18px] bg-blue-500 rounded-full border-[2px] border-[#0a0a0a] flex items-center justify-center">
                              <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7"></path></svg>
                           </div>
                        </div>
                        <div>
                          <div className="font-semibold text-[15px] text-white flex items-center gap-2">
                             STRK <span className="text-[11px] font-semibold text-blue-400 bg-blue-900/30 px-1.5 py-[1px] rounded flex items-center gap-1"><svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg> Quantum</span>
                          </div>
                          <div className="text-gray-400 text-[13px] mt-1 font-medium">{wallet.wallet_name || wallet.username || wallet.label || wallet.user_id}</div>
                        </div>
                      </div>
                      
                      <div className="font-semibold text-[15px] text-white">
                        {percentage}%
                      </div>
                      
                      <div>
                        <div className="font-semibold text-[15px] text-white">${strkPrice.toFixed(2)}</div>
                        <div className="text-red-500 text-[13px] font-medium mt-0.5">-0.00%</div>
                      </div>
                      
                      <div className="text-right">
                        <div className="font-semibold text-[15px] text-white">
                          {showBalance ? `$${(balStrk * strkPrice).toFixed(2)}` : '***'}
                        </div>
                        <div className="text-gray-400 text-sm mt-0.5 font-medium">
                          {showBalance ? `${balStrk.toFixed(4)} STRK` : '***'}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </>
          ) : (
            <>
              {/* Transactions Header */}
              <div className="grid grid-cols-[3fr_1.5fr_1.5fr_1.5fr] gap-4 px-6 py-3 text-[#999] border-b border-[#222] mb-1">
                <div className="font-medium text-[13px] uppercase tracking-wider">Transaction</div>
                <div className="font-medium text-[13px] uppercase tracking-wider">Target Address</div>
                <div className="font-medium text-[13px] uppercase tracking-wider">Status</div>
                <div className="text-right font-medium text-[13px] uppercase tracking-wider">Amount</div>
              </div>

              {/* Transactions Rows */}
              {transactions.length === 0 ? (
                 <div className="text-center py-10 text-gray-500">No transactions found for this wallet.</div>
              ) : (
                transactions.map((tx) => {
                  const isReceive = tx.type === 'receive';
                  return (
                    <div key={tx.tx_id} className="grid grid-cols-[3fr_1.5fr_1.5fr_1.5fr] gap-4 px-6 py-[18px] hover:bg-[#111] rounded-[14px] transition-colors items-center cursor-pointer border-b border-transparent hover:border-transparent">
                      <div className="flex items-center gap-[18px]">
                        <div className={`w-9 h-9 rounded-full ${isReceive ? 'bg-green-500/10 border-green-500/30' : 'bg-[#1a1a1a] border-[#333]'} border flex items-center justify-center relative flex-shrink-0 shadow-lg`}>
                           <svg className={`w-4 h-4 ${isReceive ? 'text-green-500' : 'text-gray-300'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                             <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d={isReceive ? "M19 14l-7 7m0 0l-7-7m7 7V3" : "M5 10l7-7m0 0l7 7m-7-7v18"}></path>
                           </svg>
                        </div>
                        <div>
                          <div className="font-semibold text-white">
                             {isReceive ? 'Receive' : 'Send'} STRK
                          </div>
                          <div className="text-gray-400 text-[13px] mt-1 font-medium">{formatTime(tx.created_at)}</div>
                        </div>
                      </div>
                      
                      <div className="text-[14px] font-mono text-gray-300">
                        {isReceive 
                          ? (tx.sender_account_address ? tx.sender_account_address.slice(0, 10) + '...' : '-') 
                          : (tx.to_address ? tx.to_address.slice(0, 10) + '...' : '-')
                        }
                      </div>

                      <div className="text-[13px] text-gray-400 capitalize font-medium">
                        <span className={`px-2.5 py-1 rounded-md border ${tx.status === 'confirmed' || tx.status === 'executed' ? 'border-green-500/30 text-green-400 bg-green-500/10' : tx.status === 'error' ? 'border-red-500/30 text-red-400 bg-red-500/10' : 'border-[#333] text-gray-300 bg-[#222]'}`}>
                          {tx.status}
                        </span>
                      </div>
                      
                      <div className="text-right">
                        <div className={`font-semibold text-[15px] ${isReceive ? 'text-green-500' : 'text-white'}`}>
                          {isReceive ? '+' : '-'}{showBalance ? (tx.amount_strk || "0.00") : "***"} STRK
                        </div>
                        <div className="text-gray-500 text-[13px] mt-0.5 font-medium">
                          {showBalance ? `$${((parseFloat(tx.amount_strk || 0)) * strkPrice).toFixed(2)}` : '***'}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
              
              <div className="mt-6 text-center">
                <Link to="/history" className="text-[13px] font-semibold text-white bg-[#111] border border-[#222] hover:bg-[#222] px-6 py-2.5 rounded-xl transition-colors inline-block tracking-wide">
                  View Full History
                </Link>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Wallet Detail Modal */}
      {selectedWallet && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-fade-in" onClick={() => setSelectedWallet(null)}>
              <div 
                  className="w-full max-w-lg bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-8 shadow-2xl relative"
                  onClick={e => e.stopPropagation()}
              >
                  <div className="flex justify-between items-start mb-6 pb-4 border-b border-[#1a1a1a]">
                      <div>
                          <h3 className="font-semibold text-white text-[18px] mb-1.5">{selectedWallet.wallet_name || selectedWallet.username || selectedWallet.label || selectedWallet.user_id}</h3>
                          <span className={`text-[11px] font-medium px-2.5 py-1 rounded-md tracking-wide ${selectedWallet.deployment_status === 'deployed' ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-yellow-500/10 text-yellow-500 border border-yellow-500/20'}`}>
                              {selectedWallet.deployment_status?.toUpperCase() || 'UNKNOWN'}
                          </span>
                      </div>
                      <button
                          onClick={() => setSelectedWallet(null)}
                          className="p-2 rounded-xl bg-[#111] border border-[#222] text-gray-400 hover:text-white hover:bg-[#222] transition-colors duration-200"
                      >
                          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                      </button>
                  </div>

                  <div className="space-y-4 mb-6">
                      <div className="p-4 bg-[#111] border border-[#222] rounded-xl flex items-center justify-between">
                          <div>
                              <span className="text-gray-500 block text-[11px] mb-1 font-medium tracking-wider uppercase">Balance</span>
                              <div className="font-semibold text-[15px] text-white">
                                  {balances[selectedWallet.user_id]?.balance_display || balances[selectedWallet.user_id]?.balance_strk || "0.0000"} STRK
                              </div>
                          </div>
                          <div className="text-right">
                              <span className="text-gray-500 block text-[11px] mb-1 font-medium tracking-wider uppercase">Fiat Value</span>
                              <div className="font-semibold text-[15px] text-gray-300">
                                  ${((parseFloat(balances[selectedWallet.user_id]?.balance_display || balances[selectedWallet.user_id]?.balance_strk || "0")) * strkPrice).toFixed(2)}
                              </div>
                          </div>
                      </div>

                      {selectedWallet.contract_address && (
                          <div className="p-4 bg-[#111] border border-[#222] rounded-xl">
                              <span className="text-gray-500 block text-[11px] mb-2 font-medium tracking-wider uppercase">Contract Address</span>
                              <div className="flex items-center gap-3">
                                  <div className="font-mono text-[13px] text-gray-300 break-all flex-1">
                                      {selectedWallet.contract_address}
                                  </div>
                                  <button onClick={(e) => {
                                      navigator.clipboard.writeText(selectedWallet.contract_address);
                                      const btn = e.currentTarget;
                                      const oldHTML = btn.innerHTML;
                                      btn.innerHTML = `<svg class="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>`;
                                      setTimeout(() => {
                                          if (btn) btn.innerHTML = oldHTML;
                                      }, 2000);
                                  }} className="text-gray-400 hover:text-white transition-colors shrink-0 p-1" title="Copy Address">
                                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                                  </button>
                              </div>
                          </div>
                      )}
                      
                      {selectedWallet.public_key_hash && (
                          <div className="p-4 bg-[#111] border border-[#222] rounded-xl">
                              <span className="text-gray-500 block text-[11px] mb-2 font-medium tracking-wider uppercase">Identity Hash (ML-DSA-44)</span>
                              <div className="font-mono text-[13px] text-blue-400 break-all">
                                  {selectedWallet.public_key_hash}
                              </div>
                          </div>
                      )}
                  </div>

                  {selectedWallet.contract_address && (
                      <a
                          href={`https://sepolia.voyager.online/contract/${selectedWallet.contract_address}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center justify-center gap-2 w-full py-3.5 bg-[#111] border border-[#222] rounded-[14px] text-gray-300 text-[14px] font-medium hover:bg-white hover:text-black transition-colors duration-200"
                      >
                          View on Voyager Explorer
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                      </a>
                  )}
              </div>
          </div>
      )}

    </div>
  );
}
