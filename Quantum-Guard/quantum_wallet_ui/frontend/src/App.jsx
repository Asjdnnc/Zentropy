import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import { WalletProvider } from "./context/WalletContext";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import CreateWallet from "./pages/CreateWallet";
import SendTokens from "./pages/SendTokens";
import ReceiveTokens from "./pages/ReceiveTokens";
import Transactions from "./pages/Transactions";
import TransactionHistory from "./pages/TransactionHistory";
import ProverStatus from "./pages/ProverStatus";

function App() {
  return (
    <WalletProvider>
      <Router>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/wallet" element={<CreateWallet />} />
            <Route path="/send" element={<SendTokens />} />
            <Route path="/receive" element={<ReceiveTokens />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/history" element={<TransactionHistory />} />
            <Route path="/prover" element={<ProverStatus />} />
          </Routes>
        </Layout>
      </Router>
    </WalletProvider>
  );
}

export default App;
