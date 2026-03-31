import { useState, useEffect } from "react";
import { getAuditBatches, getSystemTelemetry } from "../api/client";
function LiveTelemetryFeed() {
  const [logs, setLogs] = useState([]);
  
  useEffect(() => {
    let isMounted = true;
    
    async function fetchLogs() {
      try {
        const res = await getSystemTelemetry();
        if (isMounted && res.data?.logs) {
          const logData = res.data.logs.map((text, i) => ({ text, id: `telemetry-${i}` }));
          if (logData.length === 0) {
              const ts = new Date().toISOString().split('T')[1].slice(0, 8);
              setLogs([{ text: `<span class='text-gray-500 mr-3'>[${ts}]</span><span class='text-gray-400'>[SYS]</span> Rust Co-Processor Initialized. Awaiting payloads...`, id: 'init' }]);
          } else {
              setLogs(logData);
          }
        }
      } catch (err) {
        // Silent catch for background polling
      }
    }
    
    fetchLogs();
    const interval = setInterval(fetchLogs, 1500);
    return () => {
        isMounted = false;
        clearInterval(interval);
    };
  }, []);

  return (
    <div className="bg-[#050505] border border-[#1a1a1a] rounded-[24px] overflow-hidden shadow-2xl h-[400px] flex flex-col">
      <div className="bg-[#111] px-6 py-3 border-b border-[#222] flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500"></div>
          <div className="w-2.5 h-2.5 rounded-full bg-yellow-500"></div>
          <div className="w-2.5 h-2.5 rounded-full bg-green-500"></div>
          <span className="ml-3 text-gray-400 text-[12px] font-mono tracking-widest uppercase">Live Prover Telemetry</span>
        </div>
        <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full animate-pulse bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]"></div>
            <span className="text-green-400 text-[10px] uppercase font-bold tracking-widest">Active</span>
        </div>
      </div>
      <div className="p-6 overflow-y-auto flex-1 flex flex-col justify-end space-y-2 relative">
        <div className="absolute inset-0 pointer-events-none opacity-10 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-green-500/20 via-transparent to-transparent"></div>
        {logs.map((log) => (
          <div key={log.id} className="font-mono text-[12px] sm:text-[13px] leading-relaxed break-all transition-opacity duration-300">
            <span dangerouslySetInnerHTML={{ __html: log.text }}></span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RealBatchesTable() {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchBatches() {
      try {
        const res = await getAuditBatches({ limit: 5 });
        setBatches(res.data?.batches || []);
      } catch (err) {
        console.error("Failed to fetch batches:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchBatches();
    const interval = setInterval(fetchBatches, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="bg-[#050505] border border-[#1a1a1a] rounded-[24px] overflow-hidden shadow-2xl h-[400px] flex flex-col">
        <div className="bg-[#111] px-6 py-4 border-b border-[#222] flex items-center justify-between">
            <h3 className="text-[13px] font-semibold text-white tracking-widest uppercase flex items-center gap-2">
                <svg className="w-4 h-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                </svg>
                Recent Merkle Batches
            </h3>
        </div>
        <div className="p-0 overflow-y-auto flex-1">
            {loading ? (
                <div className="flex items-center justify-center h-full text-gray-500 text-[13px] font-mono animate-pulse">
                    Querying network...
                </div>
            ) : batches.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-gray-500 space-y-3 p-6 text-center">
                    <svg className="w-8 h-8 opacity-20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                    </svg>
                    <span className="text-[12px] font-mono tracking-widest">NO BATCHES YET</span>
                    <p className="text-[11px] text-gray-600">Execute a transfer to generate your first Merkle Root.</p>
                </div>
            ) : (
                <table className="w-full text-left border-collapse">
                    <thead className="bg-[#0a0a0a] text-gray-500 text-[10px] uppercase font-mono tracking-wider sticky top-0 z-10">
                        <tr>
                            <th className="px-6 py-3 font-medium border-b border-[#222]">Batch ID</th>
                            <th className="px-6 py-3 font-medium border-b border-[#222]">Leaves</th>
                            <th className="px-6 py-3 font-medium border-b border-[#222]">Merkle Root</th>
                        </tr>
                    </thead>
                    <tbody className="text-[13px] font-mono text-gray-300">
                        {batches.map((b) => (
                            <tr key={b.batch_id} className="border-b border-[#111] hover:bg-[#111]/50 transition-colors group">
                                <td className="px-6 py-4 whitespace-nowrap text-blue-400/80 group-hover:text-blue-400">
                                    #{b.batch_number}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <span className="bg-[#1a1a1a] text-white px-2 py-1 rounded-md text-[11px] border border-[#333]">
                                        {b.transaction_count} TX
                                    </span>
                                </td>
                                <td className="px-6 py-4 truncate max-w-[120px] sm:max-w-[200px] text-gray-500 group-hover:text-gray-300 transition-colors">
                                    {b.merkle_root}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    </div>
  );
}

function AnimatedPipeline() {
  return (
    <div className="w-full bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] p-8 md:p-12 shadow-2xl mb-12 relative overflow-hidden">
        {/* Subtle Background Math Pattern */}
        <div className="absolute inset-0 opacity-[0.03] pointer-events-none" style={{ backgroundImage: "linear-gradient(#333 1px, transparent 1px), linear-gradient(90deg, #333 1px, transparent 1px)", backgroundSize: "20px 20px" }}></div>

        <h2 className="text-[12px] text-gray-500 tracking-[0.2em] uppercase text-center font-bold mb-10 relative z-10">
            Cryptographic Data Flow
        </h2>

        <div className="flex flex-col md:flex-row items-center justify-between gap-6 relative z-10">
            
            {/* Step 1: Input */}
            <div className="flex-1 w-full bg-[#111] border border-[#222] rounded-2xl p-6 text-center transform transition hover:-translate-y-1 duration-300">
                <div className="w-12 h-12 bg-blue-500/10 border border-blue-500/30 rounded-full flex items-center justify-center mx-auto mb-4">
                    <svg className="w-5 h-5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                </div>
                <h3 className="text-white font-bold text-[14px] mb-2">User Payload</h3>
                <p className="text-gray-500 text-[12px] font-mono bg-[#1a1a1a] p-2 rounded-lg border border-[#222] inline-block">
                    ML-DSA-44: 2.4KB
                </p>
                <div className="mt-4 text-[11px] text-gray-600 font-medium">Off-chain signing</div>
            </div>

            {/* Arrow 1 */}
            <div className="hidden md:flex flex-col items-center px-2">
                <div className="text-blue-500/50 animate-pulse">
                    <svg className="w-8 h-8 translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                    </svg>
                </div>
            </div>

            {/* Step 2: Engine */}
            <div className="flex-1 w-full bg-[#111] border border-green-500/30 rounded-2xl p-6 text-center shadow-[0_0_30px_rgba(34,197,94,0.05)] transform transition hover:-translate-y-1 duration-300 relative overflow-hidden">
                <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-green-500 to-transparent opacity-50"></div>
                <div className="w-12 h-12 bg-green-500/10 border border-green-500/30 rounded-full flex items-center justify-center mx-auto mb-4 relative">
                    <div className="absolute inset-0 rounded-full animate-ping bg-green-500/20 duration-1000"></div>
                    <svg className="w-5 h-5 text-green-400 relative z-10" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                    </svg>
                </div>
                <h3 className="text-white font-bold text-[14px] mb-2 text-green-50">Rust Prover</h3>
                <p className="text-green-400/80 text-[12px] font-mono bg-green-500/5 p-2 rounded-lg border border-green-500/10 inline-block">
                    O(1) Verification
                </p>
                <div className="mt-4 text-[11px] text-gray-600 font-medium">Merkle batching</div>
            </div>

            {/* Arrow 2 */}
            <div className="hidden md:flex flex-col items-center px-2">
                <div className="text-purple-500/50 animate-pulse delay-150">
                    <svg className="w-8 h-8 translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                    </svg>
                </div>
            </div>

            {/* Step 3: Output */}
            <div className="flex-1 w-full bg-[#111] border border-[#222] rounded-2xl p-6 text-center transform transition hover:-translate-y-1 duration-300">
                <div className="w-12 h-12 bg-purple-500/10 border border-purple-500/30 rounded-full flex items-center justify-center mx-auto mb-4">
                    <svg className="w-5 h-5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                </div>
                <h3 className="text-white font-bold text-[14px] mb-2">Starknet L2</h3>
                <p className="text-gray-500 text-[12px] font-mono bg-[#1a1a1a] p-2 rounded-lg border border-[#222] inline-block">
                    Root Hash: 32B
                </p>
                <div className="mt-4 text-[11px] text-gray-600 font-medium">On-chain settlement</div>
            </div>

        </div>
    </div>
  );
}


export default function ProverStatus() {
  return (
    <div className="space-y-8 animate-fade-in text-white font-sans max-w-7xl mx-auto w-full">
      {/* 1. The Why - Hero Section */}
      <div className="mb-12 text-center max-w-4xl mx-auto mt-4 px-4">
        <div className="inline-flex items-center gap-2 px-3 py-1 bg-blue-500/10 border border-blue-500/20 rounded-full mb-6">
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
            <span className="text-[10px] uppercase tracking-widest text-blue-400 font-bold">Network Architecture</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight mb-6 text-white leading-tight">
          The Post-Quantum Engine
        </h1>
        <p className="text-gray-400 text-[15px] sm:text-[16px] leading-relaxed mb-8 max-w-3xl mx-auto">
          Starknet cannot natively verify massive <span className="text-white font-mono bg-[#1a1a1a] px-2 py-1 rounded mx-1 border border-[#333]">2,420 byte</span> ML-DSA-44 signatures efficiently. 
          Quantum-Guard acts as a zero-knowledge secure co-processor: ingesting payloads off-chain, mathematically verifying them in Rust, and compressing them 
          down to a single <span className="text-white font-mono bg-[#1a1a1a] px-2 py-1 rounded mx-1 border border-[#333]">32 byte</span> Merkle Root for cheap L2 settlement.
        </p>
      </div>

      {/* 2. The What - Animated Pipeline */}
      <AnimatedPipeline />

      {/* 3. The Evidence - Telemetry & Batches */}
      <div className="mb-6 pl-1 pt-4">
        <h2 className="text-xl font-bold tracking-tight mb-2">
          Diagnostic Telemetry
        </h2>
        <p className="text-gray-500 text-[14px]">
          Live monitor of the Rust Co-Processor and aggregated block submissions.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-stretch pb-12">
        <LiveTelemetryFeed />
        <RealBatchesTable />
      </div>
    </div>
  );
}
