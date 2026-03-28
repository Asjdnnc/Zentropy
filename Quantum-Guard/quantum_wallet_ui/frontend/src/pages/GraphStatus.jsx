import React from "react";
import TradingViewWidget from "../components/TradingViewWidget";

export default function GraphStatus() {
  return (
    <div className="space-y-8 animate-fade-in text-white font-sans max-w-7xl mx-auto w-full h-full flex flex-col">
      <div className="mb-4 pl-1 flex-shrink-0">
        <p className="text-gray-400 text-[14px]">
          Real-time STRK/USDC market rate and volume overview.
        </p>
      </div>

      <div className="bg-[#0a0a0a] border border-[#1a1a1a] overflow-hidden shadow-2xl flex-1 min-h-[600px] w-full relative group">
        <div className="absolute inset-0 z-0">
           <TradingViewWidget />
        </div>
      </div>
    </div>
  );
}
