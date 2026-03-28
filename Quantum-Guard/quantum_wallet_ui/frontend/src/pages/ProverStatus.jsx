import { useState, useEffect } from "react";
import { getHealth, getContractStatus } from "../api/client";
import StatusBadge from "../components/StatusBadge";

function CommandItem({ cmd, desc }) {
  return (
    <div className="flex items-center gap-4 group p-3 bg-[#111] border border-[#222] rounded-xl hover:border-[#333] transition-all">
      <code className="text-white font-mono text-[12px] bg-[#1a1a1a] px-3 py-1.5 rounded-md min-w-[180px] border border-[#333]">
        {cmd}
      </code>
      <span className="text-gray-400 text-[13px] font-medium group-hover:text-white transition-colors flex-1">
        {desc}
      </span>
    </div>
  );
}

export default function ProverStatus() {
  const [health, setHealth] = useState(null);
  const [contract, setContract] = useState(null);

  useEffect(() => {
    async function fetch() {
      try {
        const res = await getHealth();
        setHealth(res.data);
      } catch {
        setHealth(null);
      }
      try {
        const res = await getContractStatus();
        setContract(res.data);
      } catch {
        setContract(null);
      }
    }
    fetch();
  }, []);

  return (
    <div className="space-y-8 animate-fade-in text-white font-sans max-w-7xl mx-auto w-full">
      <div className="mb-8 pl-1">
        <h1 className="text-2xl font-bold tracking-tight mb-2">
          System Diagnostics
        </h1>
        <p className="text-gray-400 text-[14px]">
          Infrastructure health and prover status monitoring
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-10 items-stretch">
        {/* Left Column: Prover Status */}
        <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-8 md:p-10 shadow-2xl h-full flex flex-col">
          <h2 className="text-[14px] font-semibold text-white tracking-tight uppercase mb-6 border-b border-[#1a1a1a] pb-4">
            Rust Prover (Phase 2)
          </h2>
          {health ? (
            <div className="space-y-8 flex-1 flex flex-col">
              <div className="flex items-center justify-between p-5 bg-[#111] rounded-xl border border-[#222]">
                <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider">
                  Operational Status
                </span>
                <StatusBadge
                  status={health.prover_ready ? "ready" : "warning"}
                  label={health.prover_ready ? "OPTIMIZED" : "FALLBACK MODE"}
                />
              </div>

              <div className="space-y-5">
                <div>
                  <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider block mb-2">
                    Binary Path
                  </span>
                  <code className="text-gray-300 font-mono text-[13px] block bg-[#111] p-3.5 rounded-xl border border-[#222] break-all">
                    {health.prover_binary}
                  </code>
                </div>
                <div>
                    <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider block mb-2">
                        Execution Engine
                    </span>
                    <div className="p-4 bg-[#111] border border-[#222] rounded-xl flex items-center gap-3">
                        <div className={`w-2 h-2 rounded-full animate-pulse ${health.prover_ready ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]' : 'bg-yellow-500 shadow-[0_0_8px_rgba(234,179,8,0.6)]'}`}></div>
                        <span className={`text-[14px] font-semibold tracking-tight ${health.prover_ready ? "text-green-400" : "text-yellow-400"}`}>
                            {health.prover_ready ? "Native Rust (Fast)" : "Python (Slow)"}
                        </span>
                    </div>
                </div>
              </div>

              {!health.prover_ready && (
                <div className="bg-yellow-500/5 border border-yellow-500/20 rounded-[16px] p-5 mt-auto">
                  <p className="text-yellow-500 text-[13px] font-semibold mb-2 flex items-center gap-2 tracking-tight">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    Performance Warning
                  </p>
                  <p className="text-yellow-500/70 text-[12px] mb-4 leading-relaxed font-medium">
                    Rust prover binary missing. Verification will fall back to Python and run significantly slower.
                  </p>
                  <code className="text-yellow-400 font-mono text-[12px] block bg-yellow-500/10 p-3 rounded-lg border border-yellow-500/20">
                    cd zk_prover && cargo build --release
                  </code>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center flex-1 h-full min-h-[250px] text-gray-500">
              <svg className="w-10 h-10 mb-4 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
              </svg>
              <p className="text-[12px] font-bold tracking-widest">API OFFLINE</p>
            </div>
          )}
        </div>

        {/* Right Column: API & Smart Contract */}
        <div className="flex flex-col gap-10 h-full">
          {/* API Server Status */}
          <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-8 md:p-10 shadow-xl h-full">
            <h2 className="text-[14px] font-semibold text-white tracking-tight uppercase mb-6 border-b border-[#1a1a1a] pb-4">
              API Infrastructure (Phase 4)
            </h2>
            <div className="space-y-6">
              <div className="flex items-center justify-between p-5 bg-[#111] border border-[#222] rounded-xl">
                <span className="text-gray-500 text-[12px] font-medium tracking-wider">Main Backend</span>
                <StatusBadge
                  status={health ? "healthy" : "offline"}
                  label={health ? "ONLINE" : "OFFLINE"}
                />
              </div>
              {health && (
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-[#111] border border-[#222] rounded-xl">
                    <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider block mb-1">
                      Version Tag
                    </span>
                    <span className="text-white font-mono text-[14px] font-medium">
                      {health.version}
                    </span>
                  </div>
                  <div className="p-4 bg-[#111] border border-[#222] rounded-xl flex flex-col justify-center">
                    <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider block mb-2">
                      Starknet RPC Endpoint
                    </span>
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse shadow-[0_0_8px_rgba(59,130,246,0.8)] shrink-0"></div>
                      <span className="text-gray-300 font-mono text-[12px] truncate w-full">
                        {health.starknet_rpc}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Starknet Contract Status */}
          <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-8 md:p-10 shadow-xl h-full">
            <h2 className="text-[14px] font-semibold text-white tracking-tight uppercase mb-6 border-b border-[#1a1a1a] pb-4">
              Smart Contract (Phase 3)
            </h2>
            <div className="space-y-6">
              <div className="flex items-center justify-between p-5 bg-[#111] border border-[#222] rounded-xl">
                <span className="text-gray-500 text-[12px] font-medium tracking-wider">Sepolia Testnet</span>
                <StatusBadge
                  status={contract?.deployed ? "ready" : "pending"}
                  label={contract?.deployed ? "DEPLOYED" : "PENDING"}
                />
              </div>

              {contract?.contract_address ? (
                <div className="p-5 bg-[#111] border border-[#222] rounded-xl">
                  <span className="text-gray-500 text-[11px] font-medium uppercase tracking-wider block mb-2">
                    Contract Address
                  </span>
                  <p className="text-blue-400 font-mono text-[14px] break-all">
                    {contract.contract_address}
                  </p>
                </div>
              ) : (
                <div className="p-6 bg-[#111] rounded-xl border border-[#222]">
                  <p className="text-gray-300 text-[13px] mb-3 font-medium">
                    Contract status is unavailable locally from `/health`.
                  </p>
                  <p className="text-[12px] text-gray-500 leading-relaxed">
                    In v2 architecture, user wallets are deployed autonomously during registration instead of using a root registry pool. Initiate a small transfer payload to validate active configuration state directly against the target block explorer.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Build Commands Reference */}
      <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-8 md:p-10 shadow-xl">
        <h2 className="text-[14px] font-semibold text-white tracking-tight uppercase mb-6 border-b border-[#1a1a1a] pb-4">
            Command Line Utilities
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <CommandItem cmd="make setup" desc="Install system dependencies" />
          <CommandItem cmd="make test-v2" desc="Execute v2 integrity tests" />
          <CommandItem cmd="make build-phase2" desc="Compile ZK Rust prover module" />
          <CommandItem cmd="make build-phase3" desc="Compile Cairo contracts" />
          <CommandItem cmd="make deploy-contract" desc="Manual chain deployment init" />
          <CommandItem cmd="make test-all" desc="Execute global test suite wrapper" />
          <CommandItem cmd="make run-v2-api" desc="Mount core Python backend host" />
          <CommandItem cmd="make frontend-dev" desc="Mount rapid UI application host" />
        </div>
      </div>
    </div>
  );
}
