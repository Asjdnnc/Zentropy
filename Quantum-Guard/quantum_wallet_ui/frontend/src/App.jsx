import { useEffect } from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { WalletProvider } from "./context/WalletContext";
import { setApiKey, hasApiKey } from "./api/client";
import Layout from "./components/Layout";
import ErrorBoundary from "./components/ErrorBoundary";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import CreateWallet from "./pages/CreateWallet";
import SendTokens from "./pages/SendTokens";
import ReceiveTokens from "./pages/ReceiveTokens";
import Transactions from "./pages/Transactions";
import TransactionHistory from "./pages/TransactionHistory";
import ProverStatus from "./pages/ProverStatus";

function ProtectedPage({ children }) {
  if (!hasApiKey()) {
    return <Navigate to="/login" replace />;
  }
  return <Layout>{children}</Layout>;
}

function App() {
  // Optional auto-initialization for local demos only.
  useEffect(() => {
    if (!import.meta.env.DEV && !import.meta.env.VITE_API_URL) {
      console.warn('[App] VITE_API_URL is not configured for production runtime.');
    }

    const apiKey = import.meta.env.VITE_API_KEY;
    if (apiKey && !hasApiKey()) {
      setApiKey(apiKey);
      console.log('[App] API key auto-initialized from VITE_API_KEY');
    }
  }, []);

  return (
    <ErrorBoundary>
      <WalletProvider>
        <Router>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />

            <Route path="/dashboard" element={<ProtectedPage><Dashboard /></ProtectedPage>} />
            <Route path="/wallet" element={<ProtectedPage><CreateWallet /></ProtectedPage>} />
            <Route path="/send" element={<ProtectedPage><SendTokens /></ProtectedPage>} />
            <Route path="/receive" element={<ProtectedPage><ReceiveTokens /></ProtectedPage>} />
            <Route path="/transactions" element={<ProtectedPage><Transactions /></ProtectedPage>} />
            <Route path="/history" element={<ProtectedPage><TransactionHistory /></ProtectedPage>} />
            <Route path="/prover" element={<ProtectedPage><ProverStatus /></ProtectedPage>} />
            <Route path="*" element={<Navigate to={hasApiKey() ? "/dashboard" : "/login"} replace />} />
          </Routes>
        </Router>
      </WalletProvider>
    </ErrorBoundary>
  );
}

export default App;
