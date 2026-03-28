import React, { useState } from "react";
import Sidebar from "./Sidebar";
import { useWallet } from "../context/WalletContext";

export default function Layout({ children }) {
  const { orgName } = useWallet();
  const [showDropdown, setShowDropdown] = useState(false);
  
  // Safely fetch auth token from active environment memory
  const apiKey = localStorage.getItem("token") || "No Active API Key found";

  return (
    <div className="min-h-screen bg-black text-white font-sans selection:bg-blue-500 selection:text-white">
      <Sidebar />
      <main className="md:ml-[260px] min-h-screen flex flex-col">
        <header className="h-[72px] bg-[#050505]/95 backdrop-blur-md border-b border-[#1a1a1a] sticky top-0 z-40 px-8 flex items-center justify-between">
          <h2 className="text-[15px] font-semibold tracking-tight text-white">
           
          </h2>
          <div className="flex items-center gap-4 relative">
            <div className="flex flex-col items-end">
              {orgName && (
                <span className="text-[13px] font-medium text-gray-400">
                  {orgName}
                </span>
              )}
            </div>
            
            {/* Interactive Profile Icon */}
            <button 
                onClick={() => setShowDropdown(!showDropdown)}
                className="w-8 h-8 rounded-full bg-[#111] border border-[#222] outline-none flex items-center justify-center hover:bg-[#222] hover:border-[#333] transition-all cursor-pointer relative z-50 shadow-sm"
            >
                <svg className="w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
            </button>
            
            {/* API Key Modal Window */}
            {showDropdown && (
                <>
                    {/* Invisible overlay to catch outside clicks */}
                    <div 
                        className="fixed inset-0 z-40" 
                        onClick={() => setShowDropdown(false)}
                    />
                    
                    <div className="absolute top-[140%] right-0 w-[300px] bg-[#0a0a0a] border border-[#1a1a1a] rounded-[18px] p-5 shadow-[0_10px_40px_rgba(0,0,0,0.8)] animate-fade-in z-50">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-[11px] font-medium text-gray-500 uppercase tracking-widest">Active API Key</h3>
                        </div>
                        
                        <div className="p-3 bg-[#111] border border-[#222] rounded-xl flex items-center gap-3">
                            <code className="text-[13px] font-mono text-blue-400 truncate flex-1 min-w-0" title={apiKey}>
                                {apiKey}
                            </code>
                            <button 
                                onClick={(e) => {
                                    e.stopPropagation();
                                    navigator.clipboard.writeText(apiKey);
                                    
                                    // Visual tick effect
                                    const btn = e.currentTarget;
                                    const origHTML = btn.innerHTML;
                                    btn.innerHTML = `<svg class="w-3.5 h-3.5 text-black" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" /></svg>`;
                                    btn.classList.add('bg-white');
                                    btn.classList.remove('bg-[#222]');
                                    
                                    setTimeout(() => {
                                        if (btn) {
                                            btn.innerHTML = origHTML;
                                            btn.classList.remove('bg-white');
                                            btn.classList.add('bg-[#222]');
                                        }
                                    }, 1000);
                                }}
                                className="p-2 bg-[#222] hover:bg-white text-gray-400 hover:text-black rounded-lg transition-colors border border-transparent shrink-0 flex items-center justify-center focus:outline-none"
                                title="Copy API Key"
                            >
                                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                            </button>
                        </div>
                        <p className="text-[#555] text-[11px] mt-4 leading-relaxed font-medium">
                            Use this raw token to authenticate programmatic external CLI or API calls against the active session.
                        </p>
                    </div>
                </>
            )}
          </div>
        </header>
        <div className="p-8 max-w-7xl mx-auto w-full flex-grow">{children}</div>
      </main>
    </div>
  );
}
