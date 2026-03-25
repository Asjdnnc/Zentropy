import React from "react";
import Sidebar from "./Sidebar";
import { getApiBase } from "../api/client";

export default function Layout({ children }) {
  const apiBase = getApiBase() || "(relative /api)";

  return (
    <div className="min-h-screen bg-bg-dark text-white font-inter selection:bg-neon-cyan selection:text-black">
      <Sidebar />
      <main className="md:ml-64 min-h-screen">
        <header className="h-16 glass-panel border-b border-white/5 sticky top-0 z-40 px-8 flex items-center justify-between backdrop-blur-md">
          <h2 className="text-xl font-orbitron text-white/80">
            Wallet Dashboard
          </h2>
          <div className="flex items-center gap-4">
            <div className="flex flex-col items-end">
              <span className="text-xs text-neon-purple font-medium">
                API Endpoint
              </span>
              <span className="text-[10px] text-gray-500 font-mono">
                {apiBase}
              </span>
            </div>
            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-cyan-500 to-blue-500 border border-white/20"></div>
          </div>
        </header>
        <div className="p-8 max-w-7xl mx-auto">{children}</div>
      </main>
    </div>
  );
}
