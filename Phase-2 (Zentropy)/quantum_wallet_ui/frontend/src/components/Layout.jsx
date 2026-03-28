import React, { useState } from "react";
import Sidebar from "./Sidebar";
import { useWallet } from "../context/WalletContext";
import { verifyMpin, setMpin, getApiKey } from "../api/client";

export default function Layout({ children }) {
  const { orgName, activeWallet, refreshWallets } = useWallet();
  const [showDropdown, setShowDropdown] = useState(false);
  
  // Modals state
  const [showRevealModal, setShowRevealModal] = useState(false);
  const [showResetModal, setShowResetModal] = useState(false);

  // Profile Menu Dropdown Helpers
  const handleDropdownToggle = () => setShowDropdown(!showDropdown);

  // ─── REVEAL API KEY STATE & LOGIC ────────────────────────────────
  const [isApiKeyRevealed, setIsApiKeyRevealed] = useState(false);
  const [mpinInput, setMpinInput] = useState("");
  const [mpinError, setMpinError] = useState("");
  const [isVerifying, setIsVerifying] = useState(false);

  // Safely fetch auth token from active environment memory
  const apiKey = getApiKey() || localStorage.getItem("token") || "No Active API Key found";

  const handleRevealAction = () => {
      setShowDropdown(false);
      if (!activeWallet) {
          alert("Please create or select an active wallet first.");
          return;
      }
      if (!activeWallet.has_mpin) {
          alert("Security: Your active wallet does not have an MPIN configured. Please create an MPIN during your first transaction.");
          return;
      }
      setIsApiKeyRevealed(false);
      setMpinInput("");
      setMpinError("");
      setShowRevealModal(true);
  };

  const handleRevealMpinSubmit = async () => {
      if (!mpinInput) return;
      setIsVerifying(true);
      setMpinError("");
      try {
          const res = await verifyMpin(activeWallet.user_id, mpinInput);
          if (res.data.valid) {
              setIsApiKeyRevealed(true);
          }
      } catch (err) {
          setMpinError(err.readableMessage || "Invalid MPIN. Please try again.");
      } finally {
          setIsVerifying(false);
      }
  };

  // ─── RESET MPIN STATE & LOGIC ────────────────────────────────────
  const [resetStep, setResetStep] = useState(1); // 1: verify api key, 2: set new mpin
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [newMpinInput, setNewMpinInput] = useState("");
  const [resetError, setResetError] = useState("");
  const [isResetting, setIsResetting] = useState(false);

  const handleResetAction = () => {
      setShowDropdown(false);
      if (!activeWallet) {
          alert("Please create or select an active wallet first.");
          return;
      }
      setResetStep(1);
      setApiKeyInput("");
      setNewMpinInput("");
      setResetError("");
      setShowResetModal(true);
  };

  const handleResetApiKeySubmit = () => {
      if (!apiKeyInput) return;
      if (apiKeyInput === apiKey) {
          setResetStep(2);
          setResetError("");
      } else {
          setResetError("Invalid API Key");
      }
  };

  const handleResetMpinSubmit = async () => {
      if (newMpinInput.length < 4) return;
      setIsResetting(true);
      setResetError("");
      try {
          await setMpin(activeWallet.user_id, newMpinInput);
          await refreshWallets(); // Refresh context to register the new MPIN configuration
          setShowResetModal(false);
          alert("Success! Your MPIN has been securely reset.");
      } catch (err) {
          setResetError(err.readableMessage || "Failed to reset MPIN.");
      } finally {
          setIsResetting(false);
      }
  };

  return (
    <div className="min-h-screen bg-black text-white font-sans selection:bg-blue-500 selection:text-white relative">
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
                onClick={handleDropdownToggle}
                className="w-8 h-8 rounded-full bg-[#111] border border-[#222] outline-none flex items-center justify-center hover:bg-[#222] hover:border-[#333] transition-all cursor-pointer relative z-50 shadow-sm"
            >
                <svg className="w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
            </button>
            
            {/* Profile Menu Dropdown */}
            {showDropdown && (
                <>
                    <div className="fixed inset-0 z-40" onClick={() => setShowDropdown(false)} />
                    <div className="absolute top-[140%] right-0 w-[220px] bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl p-2 shadow-2xl animate-fade-in z-50">
                        <button 
                            onClick={handleResetAction}
                            className="w-full text-left px-4 py-2.5 text-[13px] font-medium text-gray-300 hover:text-white hover:bg-[#111] rounded-lg transition-colors flex items-center gap-2"
                        >
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                            Reset MPIN
                        </button>
                        <button 
                            onClick={handleRevealAction}
                            className="w-full text-left px-4 py-2.5 text-[13px] font-medium text-gray-300 hover:text-white hover:bg-[#111] rounded-lg transition-colors flex items-center gap-2 mt-1"
                        >
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
                            Reveal API Key
                        </button>
                    </div>
                </>
            )}
            
          </div>
        </header>
        <div className="p-8 max-w-7xl mx-auto w-full flex-grow">{children}</div>
      </main>

      {/* Reveal API Key Modal (Moved outside header for proper fixed centering) */}
      {showRevealModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
              <div className="w-full max-w-sm bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] overflow-hidden shadow-2xl relative p-8">
                  
                  <div className="flex justify-between items-center mb-6">
                      <div className="w-12 h-12 bg-blue-500/10 rounded-2xl flex items-center justify-center border border-blue-500/20">
                          <svg className="w-6 h-6 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg>
                      </div>
                      <button onClick={() => setShowRevealModal(false)} className="text-gray-500 hover:text-white transition-colors">
                          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" /></svg>
                      </button>
                  </div>
                  
                  {!isApiKeyRevealed ? (
                      <>
                          <h2 className="text-xl font-medium text-white mb-2 tracking-tight">Authorization Required</h2>
                          <p className="text-sm text-gray-400 mb-6 leading-relaxed">
                              Enter your <span className="text-white font-medium">4-6 digit MPIN</span> to reveal the Organization API Key.
                          </p>

                          <div className="space-y-4">
                              <div className="space-y-2">
                                  <input
                                      type="password"
                                      value={mpinInput}
                                      onChange={(e) => setMpinInput(e.target.value.replace(/\D/g, '').substring(0, 6))}
                                      placeholder="Enter MPIN"
                                      className={`w-full bg-[#111] border ${mpinError ? 'border-red-500/50 focus:border-red-500 focus:ring-red-500/20' : 'border-[#222] focus:border-[#333] focus:ring-white/5'} rounded-xl px-4 py-3.5 text-white placeholder-gray-600 outline-none transition-all text-center tracking-[0.5em] text-lg font-medium`}
                                      autoFocus
                                      onKeyDown={(e) => {
                                          if (e.key === 'Enter') handleRevealMpinSubmit();
                                      }}
                                  />
                                  {mpinError && (
                                      <p className="text-red-400 text-[13px] text-center font-medium animate-fade-in">{mpinError}</p>
                                  )}
                              </div>
                              
                              <button
                                  onClick={handleRevealMpinSubmit}
                                  disabled={isVerifying || mpinInput.length < 4}
                                  className="w-full bg-white text-black font-medium px-4 py-3.5 rounded-xl hover:bg-gray-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                              >
                                  {isVerifying ? (
                                      <>
                                          <svg className="animate-spin h-5 w-5 border-2 border-black border-t-transparent rounded-full" viewBox="0 0 24 24"></svg>
                                          Verifying...
                                      </>
                                  ) : (
                                      'Reveal API Key'
                                  )}
                              </button>
                          </div>
                      </>
                  ) : (
                      <>
                          <h2 className="text-xl font-medium text-white mb-2 tracking-tight">Active API Key</h2>
                          <p className="text-sm text-green-400 mb-6 font-medium">Authorization successful.</p>
                          
                          <div className="p-3 bg-[#111] border border-[#222] rounded-xl flex items-center gap-3 w-full mb-6">
                              <code className="text-[13px] font-mono text-blue-400 truncate flex-1 min-w-0" title={apiKey}>
                                  {apiKey}
                              </code>
                              <button 
                                  onClick={(e) => {
                                      navigator.clipboard.writeText(apiKey);
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
                                  className="p-2 bg-[#222] hover:bg-white text-gray-400 hover:text-black rounded-lg transition-colors border border-transparent shrink-0 flex items-center justify-center outline-none"
                                  title="Copy API Key"
                              >
                                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                              </button>
                          </div>
                          
                          <button 
                              onClick={() => setShowRevealModal(false)}
                              className="w-full bg-[#222] text-white font-medium px-4 py-3.5 rounded-xl hover:bg-[#333] transition-colors"
                          >
                              Done
                          </button>
                      </>
                  )}
              </div>
          </div>
      )}

      {/* Reset MPIN Modal (Moved outside header for proper fixed centering) */}
      {showResetModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
              <div className="w-full max-w-sm bg-[#0a0a0a] border border-[#1a1a1a] rounded-[24px] overflow-hidden shadow-2xl relative p-8">
                  <div className="flex justify-between items-center mb-6">
                      <div className="w-12 h-12 bg-purple-500/10 rounded-2xl flex items-center justify-center border border-purple-500/20">
                          <svg className="w-6 h-6 text-purple-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg>
                      </div>
                      <button onClick={() => setShowResetModal(false)} className="text-gray-500 hover:text-white transition-colors">
                          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" /></svg>
                      </button>
                  </div>

                  {resetStep === 1 ? (
                      <>
                          <h2 className="text-xl font-medium text-white mb-2 tracking-tight">Reset MPIN</h2>
                          <p className="text-sm text-gray-400 mb-6 leading-relaxed">
                              Please enter your <span className="text-white font-medium">Organization API Key</span> to proceed.
                          </p>

                          <div className="space-y-4">
                              <div className="space-y-2">
                                  <input
                                      type="password"
                                      value={apiKeyInput}
                                      onChange={(e) => setApiKeyInput(e.target.value)}
                                      placeholder="Paste API Key here..."
                                      className={`w-full bg-[#111] border ${resetError ? 'border-red-500/50 focus:border-red-500 focus:ring-red-500/20' : 'border-[#222] focus:border-[#333] focus:ring-white/5'} rounded-xl px-4 py-3.5 text-white placeholder-gray-600 outline-none transition-all text-[13px] font-mono`}
                                      autoFocus
                                      onKeyDown={(e) => {
                                          if (e.key === 'Enter') handleResetApiKeySubmit();
                                      }}
                                  />
                                  {resetError && (
                                      <p className="text-red-400 text-[13px] text-center font-medium animate-fade-in">{resetError}</p>
                                  )}
                              </div>
                              
                              <button
                                  onClick={handleResetApiKeySubmit}
                                  disabled={!apiKeyInput}
                                  className="w-full bg-white text-black font-medium px-4 py-3.5 rounded-xl hover:bg-gray-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                              >
                                  Verify API Key
                              </button>
                          </div>
                      </>
                  ) : (
                      <>
                          <h2 className="text-xl font-medium text-white mb-2 tracking-tight">Set New MPIN</h2>
                          <p className="text-sm text-gray-400 mb-6 leading-relaxed">
                              Enter your new <span className="text-white font-medium">4-6 digit</span> MPIN code.
                          </p>

                          <div className="space-y-4">
                              <div className="space-y-2">
                                  <input
                                      type="password"
                                      value={newMpinInput}
                                      onChange={(e) => setNewMpinInput(e.target.value.replace(/\D/g, '').substring(0, 6))}
                                      placeholder="Enter New MPIN"
                                      className={`w-full bg-[#111] border ${resetError ? 'border-red-500/50 focus:border-red-500 focus:ring-red-500/20' : 'border-[#222] focus:border-[#333] focus:ring-white/5'} rounded-xl px-4 py-3.5 text-white placeholder-gray-600 outline-none transition-all text-center tracking-[0.5em] text-lg font-medium`}
                                      autoFocus
                                      onKeyDown={(e) => {
                                          if (e.key === 'Enter') handleResetMpinSubmit();
                                      }}
                                  />
                                  {resetError && (
                                      <p className="text-red-400 text-[13px] text-center font-medium animate-fade-in">{resetError}</p>
                                  )}
                              </div>
                              
                              <button
                                  onClick={handleResetMpinSubmit}
                                  disabled={isResetting || newMpinInput.length < 4}
                                  className="w-full bg-white text-black font-medium px-4 py-3.5 rounded-xl hover:bg-gray-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                              >
                                  {isResetting ? (
                                      <>
                                          <svg className="animate-spin h-5 w-5 border-2 border-black border-t-transparent rounded-full" viewBox="0 0 24 24"></svg>
                                          Updating...
                                      </>
                                  ) : (
                                      'Save New MPIN'
                                  )}
                              </button>
                          </div>
                      </>
                  )}
              </div>
          </div>
      )}

    </div>
  );
}
