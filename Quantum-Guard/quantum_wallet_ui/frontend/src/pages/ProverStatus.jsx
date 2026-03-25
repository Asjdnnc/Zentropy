import { useState, useEffect } from "react";
import { getHealth, getContractStatus } from "../api/client";
import StatusBadge from "../components/StatusBadge";
import Card from "../components/Card";

function CommandItem({ cmd, desc }) {
  return (
    <div className="flex items-center gap-4 group hover:bg-white/5 p-2 rounded transition-colors">
      <code className="text-neon-cyan font-mono text-sm bg-black/40 border border-neon-cyan/20 px-3 py-1.5 rounded min-w-[220px] group-hover:border-neon-cyan/50 transition-colors shadow-[0_0_5px_rgba(0,0,0,0.5)]">
        {cmd}
      </code>
      <span className="text-gray-400 text-sm group-hover:text-gray-200">
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
    <div className="space-y-8 animate-fade-in">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold font-orbitron text-white">
            System Diagnostics
          </h1>
          <p className="text-gray-400 mt-1">
            Infrastructure health and prover status monitoring
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Prover Status */}
        <Card variant="purple" title="RUST PROVER (PHASE 2)" className="h-full">
          {health ? (
            <div className="space-y-6">
              <div className="flex items-center justify-between p-4 bg-white/5 rounded-lg border border-white/5">
                <span className="text-gray-400 text-sm uppercase tracking-wider">
                  Operational Status
                </span>
                <StatusBadge
                  status={health.prover_ready ? "ready" : "warning"}
                  label={health.prover_ready ? "OPTIMIZED" : "FALLBACK MODE"}
                />
              </div>

              <div className="space-y-4">
                <div>
                  <span className="text-gray-500 text-xs uppercase tracking-wider block mb-1">
                    Binary Path
                  </span>
                  <code className="text-gray-300 font-mono text-xs block bg-black/30 p-2 rounded border border-white/5">
                    {health.prover_binary}
                  </code>
                </div>
                <div className="flex gap-4">
                  <div className="flex-1">
                    <span className="text-gray-500 text-xs uppercase tracking-wider block mb-1">
                      Execution Engine
                    </span>
                    <span
                      className={`text-sm font-bold ${health.prover_ready ? "text-neon-green" : "text-yellow-400"}`}
                    >
                      {health.prover_ready
                        ? "Native Rust (Fast)"
                        : "Python (Slow)"}
                    </span>
                  </div>
                </div>
              </div>

              {!health.prover_ready && (
                <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-4">
                  <p className="text-yellow-400 text-sm mb-2 flex items-center gap-2">
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                      />
                    </svg>
                    Performance Warning
                  </p>
                  <p className="text-gray-400 text-xs mb-2">
                    Rust prover binary missing. Verification will be slow.
                  </p>
                  <code className="text-yellow-300 font-mono text-xs block bg-black/30 p-2 rounded">
                    cd zk_prover && cargo build --release
                  </code>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-48 text-gray-500">
              <svg
                className="w-12 h-12 mb-3 opacity-50"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1}
                  d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"
                />
              </svg>
              <p>API SERVER DISCONNECTED</p>
            </div>
          )}
        </Card>

        {/* API Server Status */}
        <div className="space-y-8">
          <Card variant="default" title="API INFRASTRUCTURE (PHASE 4)">
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-4 border-b border-white/5">
                <span className="text-gray-400 text-sm">Main Backend</span>
                <StatusBadge
                  status={health ? "healthy" : "offline"}
                  label={health ? "ONLINE" : "OFFLINE"}
                />
              </div>
              {health && (
                <>
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-gray-500">Version Tag</span>
                    <span className="text-white font-mono">
                      {health.version}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500 text-xs block mb-1">
                      Starknet RPC Endpoint
                    </span>
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
                      <span className="text-gray-300 font-mono text-xs truncate">
                        {health.starknet_rpc}
                      </span>
                    </div>
                  </div>
                </>
              )}
            </div>
          </Card>

          {/* Starknet Contract Status */}
          <Card variant="default" title="SMART CONTRACT (PHASE 3)">
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-4 border-b border-white/5">
                <span className="text-gray-400 text-sm">Sepolia Testnet</span>
                <StatusBadge
                  status={contract?.deployed ? "ready" : "pending"}
                  label={contract?.deployed ? "DEPLOYED" : "PENDING"}
                />
              </div>

              {contract?.contract_address ? (
                <div>
                  <span className="text-gray-500 text-xs uppercase tracking-wider block mb-1">
                    Contract Address
                  </span>
                  <p className="text-indigo-300 font-mono text-xs break-all bg-indigo-900/10 p-2 rounded border border-indigo-500/20">
                    {contract.contract_address}
                  </p>
                </div>
              ) : (
                <div className="p-4 bg-white/5 rounded-lg border border-white/10">
                  <p className="text-gray-400 text-sm mb-4">
                    Contract status is unavailable from health metadata.
                  </p>
                  <p className="text-xs text-gray-500 mt-2">
                    In v2, user wallets are deployed automatically during registration.
                    Use the transfer smoke flow or user deployment-status endpoint to validate chain deployment.
                  </p>
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>

      {/* Build Commands Reference */}
      <Card
        title="DEVELOPER COMMANDS"
        className="opacity-80 hover:opacity-100 transition-opacity"
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2">
          <CommandItem cmd="make setup" desc="Install dependencies" />
          <CommandItem cmd="make test-v2" desc="Run v2 backend tests" />
          <CommandItem cmd="make build-phase2" desc="Compile Rust prover" />
          <CommandItem cmd="make build-phase3" desc="Compile Cairo contract" />
          <CommandItem cmd="make deploy-contract" desc="Manual deployment" />
          <CommandItem cmd="make test-all" desc="Full test suite" />
          <CommandItem cmd="make run-v2-api" desc="Start v2 API server" />
          <CommandItem cmd="make frontend-dev" desc="Start UI server" />
        </div>
      </Card>
    </div>
  );
}
