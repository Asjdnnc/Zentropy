import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { listWallets, getContractStatus, getTransactionHistory, getWalletBalance } from '../api/client';

const WalletContext = createContext(null);

export function WalletProvider({ children }) {
    const [wallets, setWallets] = useState([]);
    const [activeWallet, setActiveWallet] = useState(null);
    const [contract, setContract] = useState(null);
    const [transactions, setTransactions] = useState([]);
    const [txCount, setTxCount] = useState(0);
    const [balances, setBalances] = useState({}); // { label: balanceData }
    const [loading, setLoading] = useState(true);
    const balanceIntervalRef = useRef(null);

    const refreshWallets = useCallback(async () => {
        try {
            const res = await listWallets();
            const w = res.data.wallets || [];
            setWallets(w);
            // Auto-select first wallet if none active
            if (!activeWallet && w.length > 0) {
                setActiveWallet(w[0]);
            }
            return w;
        } catch {
            return [];
        }
    }, [activeWallet]);

    const refreshContract = useCallback(async () => {
        try {
            const res = await getContractStatus();
            setContract(res.data);
        } catch {
            setContract(null);
        }
    }, []);

    const refreshTransactions = useCallback(async (label = null, limit = 50) => {
        try {
            const params = { limit };
            if (label) params.label = label;
            const res = await getTransactionHistory(params);
            setTransactions(res.data.transactions || []);
            setTxCount(res.data.total || 0);
        } catch {
            // API offline
        }
    }, []);

    const refreshBalance = useCallback(async (label, forceRefresh = false) => {
        try {
            const res = await getWalletBalance(label, forceRefresh);
            setBalances(prev => ({
                ...prev,
                [label]: res.data,
            }));
            return res.data;
        } catch {
            return null;
        }
    }, []);

    const refreshAllBalances = useCallback(async (walletList = null) => {
        const w = walletList || wallets;
        const deployed = w.filter(wallet => wallet.contract_address);
        await Promise.all(deployed.map(wallet => refreshBalance(wallet.label)));
    }, [wallets, refreshBalance]);

    const refreshAll = useCallback(async () => {
        setLoading(true);
        const [fetchedWallets] = await Promise.all([
            refreshWallets(),
            refreshContract(),
            refreshTransactions(),
        ]);
        // Refresh balances for deployed wallets
        if (fetchedWallets.length > 0) {
            await refreshAllBalances(fetchedWallets);
        }
        setLoading(false);
    }, [refreshWallets, refreshContract, refreshTransactions, refreshAllBalances]);

    // Initial load
    useEffect(() => {
        refreshAll();
    }, []);  // eslint-disable-line react-hooks/exhaustive-deps

    // Auto-refresh balances every 30 seconds
    useEffect(() => {
        if (balanceIntervalRef.current) {
            clearInterval(balanceIntervalRef.current);
        }

        const deployedWallets = wallets.filter(w => w.contract_address);
        if (deployedWallets.length > 0) {
            balanceIntervalRef.current = setInterval(() => {
                refreshAllBalances();
            }, 30000);
        }

        return () => {
            if (balanceIntervalRef.current) {
                clearInterval(balanceIntervalRef.current);
            }
        };
    }, [wallets, refreshAllBalances]);

    const value = {
        wallets,
        activeWallet,
        setActiveWallet,
        contract,
        transactions,
        txCount,
        balances,
        loading,
        refreshWallets,
        refreshContract,
        refreshTransactions,
        refreshBalance,
        refreshAllBalances,
        refreshAll,
    };

    return (
        <WalletContext.Provider value={value}>
            {children}
        </WalletContext.Provider>
    );
}

export function useWallet() {
    const ctx = useContext(WalletContext);
    if (!ctx) throw new Error('useWallet must be used within WalletProvider');
    return ctx;
}

export default WalletContext;
