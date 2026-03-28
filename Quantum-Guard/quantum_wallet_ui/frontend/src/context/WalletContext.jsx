/* eslint-disable react-refresh/only-export-components */

import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import {
    listWallets,
    getWalletInfo,
    getContractStatus,
    getTransactionHistory,
    getWalletBalance,
    getActiveUserId,
    setActiveUserId,
    getOrgDetails,
} from '../api/client';

const WalletContext = createContext(null);

export function WalletProvider({ children }) {
    const [wallets, setWallets] = useState([]);
    const [activeWallet, setActiveWalletState] = useState(null);
    const [contract, setContract] = useState(null);
    const [transactions, setTransactions] = useState([]);
    const [txCount, setTxCount] = useState(0);
    const [balances, setBalances] = useState({}); // { user_id: walletData }
    const [orgName, setOrgName] = useState("");
    const [loading, setLoading] = useState(true);
    const balanceIntervalRef = useRef(null);
    const isMountedRef = useRef(true);
    const isPageVisibleRef = useRef(true);

    // Wrap setActiveWallet so it also persists the user_id to localStorage
    const setActiveWallet = useCallback((wallet) => {
        setActiveWalletState(wallet);
        if (wallet?.user_id) {
            setActiveUserId(wallet.user_id);
        }
    }, []);

    const refreshWallets = useCallback(async (options = {}) => {
        try {
            const res = await listWallets(50, 0, { signal: options.signal });
            // v2 returns { total, users: [...] }
            const users = res.data.users || res.data.wallets || [];

            // Fetch wallet details (contract_address, deployment_status) for each user
            const enriched = await Promise.all(
                users.map(async (u) => {
                    try {
                        const walletRes = await getWalletInfo(u.user_id, { signal: options.signal });
                        return {
                            // keep label field for backwards compat with UI components
                            label: u.user_id,
                            user_id: u.user_id,
                            username: u.username || u.email || u.user_id,
                            ...walletRes.data,
                        };
                    } catch {
                        return {
                            label: u.user_id,
                            user_id: u.user_id,
                            username: u.username || u.email || u.user_id,
                            contract_address: null,
                            deployment_status: 'unknown',
                        };
                    }
                })
            );

            if (!isMountedRef.current) return [];
            setWallets(enriched);

            // Auto-select persisted active user or first wallet
            const persistedId = getActiveUserId();
            const persisted = enriched.find((w) => w.user_id === persistedId);
            if (persisted) {
                setActiveWalletState(persisted);
            } else if (!activeWallet && enriched.length > 0) {
                setActiveWallet(enriched[0]);
            }

            return enriched;
        } catch {
            return [];
        }
    }, [activeWallet, setActiveWallet]);

    const refreshContract = useCallback(async (options = {}) => {
        try {
            const res = await getContractStatus({ signal: options.signal });
            if (!isMountedRef.current) return;
            setContract(res.data);
        } catch {
            if (!isMountedRef.current) return;
            setContract(null);
        }
    }, []);

    const refreshTransactions = useCallback(async (userId = null, limit = 50, options = {}) => {
        try {
            const uid = userId || getActiveUserId();
            if (!uid) return;
            const res = await getTransactionHistory({ user_id: uid, limit, signal: options.signal });
            if (!isMountedRef.current) return;
            setTransactions(res.data.transactions || []);
            setTxCount(res.data.total || 0);
        } catch {
            // API offline or no user selected yet
        }
    }, []);

    const refreshBalance = useCallback(async (userId = null, options = {}) => {
        const uid = userId || getActiveUserId();
        if (!uid) return null;
        try {
            const res = await getWalletBalance(uid, { signal: options.signal });
            if (!isMountedRef.current) return null;
            setBalances((prev) => ({ ...prev, [uid]: res.data }));
            return res.data;
        } catch {
            return null;
        }
    }, []);

    const refreshAllBalances = useCallback(async (walletList = null, options = {}) => {
        if (!isPageVisibleRef.current) return;
        const w = walletList || wallets;
        const deployed = w.filter((wallet) => wallet.contract_address);
        await Promise.all(deployed.map((wallet) => refreshBalance(wallet.user_id, options)));
    }, [wallets, refreshBalance]);

    const refreshAll = useCallback(async (options = {}) => {
        setLoading(true);
        try {
            const orgRes = await getOrgDetails(options);
            if (isMountedRef.current) setOrgName(orgRes.data.org_name || "");
        } catch {
            // keep silent or handle
        }
        
        const [fetchedWallets] = await Promise.all([
            refreshWallets(options),
            refreshContract(options),
            refreshTransactions(null, 50, options),
        ]);
        if (fetchedWallets.length > 0) {
            await refreshAllBalances(fetchedWallets, options);
        }
        if (!isMountedRef.current) return;
        setLoading(false);
    }, [refreshWallets, refreshContract, refreshTransactions, refreshAllBalances]);

    useEffect(() => {
        isMountedRef.current = true;
        isPageVisibleRef.current = typeof document === 'undefined' ? true : !document.hidden;
        return () => {
            isMountedRef.current = false;
        };
    }, []);

    useEffect(() => {
        const onVisibilityChange = () => {
            isPageVisibleRef.current = !document.hidden;
            if (isPageVisibleRef.current) {
                refreshAllBalances();
            }
        };

        document.addEventListener('visibilitychange', onVisibilityChange);
        return () => document.removeEventListener('visibilitychange', onVisibilityChange);
    }, [refreshAllBalances]);

    // Initial load
    useEffect(() => {
        const abortController = new AbortController();
        const timer = setTimeout(() => {
            refreshAll({ signal: abortController.signal });
        }, 0);
        return () => {
            abortController.abort();
            clearTimeout(timer);
        };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Auto-refresh balances every 30 seconds
    useEffect(() => {
        if (balanceIntervalRef.current) {
            clearInterval(balanceIntervalRef.current);
        }
        const deployedWallets = wallets.filter((w) => w.contract_address);
        if (deployedWallets.length > 0 && isPageVisibleRef.current) {
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
        orgName,
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
