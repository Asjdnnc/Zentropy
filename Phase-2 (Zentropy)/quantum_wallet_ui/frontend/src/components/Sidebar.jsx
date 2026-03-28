import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { clearApiKey, clearActiveUserId } from "../api/client";

export default function Sidebar() {
  const navigate = useNavigate();

  const linkClass = ({ isActive }) =>
    `flex items-center gap-3 px-4 py-2.5 rounded-xl text-[13px] font-medium transition-colors ${isActive
      ? "bg-[#111] text-white border border-[#222]"
      : "text-gray-500 hover:text-white hover:bg-[#0a0a0a] border border-transparent"
    }`;

  const navItems = [
    {
      to: "/dashboard",
      label: "Dashboard",
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
        </svg>
      ),
    },
    {
      to: "/wallet",
      label: "Create Wallet",
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
      ),
    },
    {
      to: "/send",
      label: "Send STRK",
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
    },
    {
      to: "/receive",
      label: "Receive",
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
      ),
    },
    {
      to: "/history",
      label: "History",
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    {
      to: "/prover",
      label: "Prover Status",
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    // {
    //   to: "/graph",
    //   label: "Graph Status",
    //   icon: (
    //     <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    //       <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    //     </svg>
    //   ),
    // },
  ];

  return (
    <aside className="w-[260px] bg-[#000000] border-r border-[#1a1a1a] hidden md:flex flex-col h-screen fixed left-0 top-0 overflow-y-auto z-50">
      
      {/* Brand Header */}
      <div className="h-[72px] px-8 flex items-center gap-3 border-b border-[#1a1a1a]">
        <a href="/"><div className="w-8 h-8 bg-white text-black flex items-center justify-center rounded-md font-extrabold text-[12px] tracking-tighter">Zen</div></a>
       <a href="/"> <h1 className="font-bold text-lg tracking-tight text-white mt-0.5">
          ZENTROPY
        </h1></a>
      </div>

      <nav className="flex-1 px-4 py-6 space-y-1">
        <p className="px-3 text-[11px] font-semibold text-gray-600 uppercase tracking-widest mb-4">
          Platform
        </p>
        {navItems.map((item) => (
          <NavLink key={item.to} to={item.to} className={linkClass}>
            {item.icon}
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer Meta block */}
      <div className="p-4 border-t border-[#1a1a1a]">
        <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></div>
            <span className="text-[12px] font-medium text-gray-400">System Online</span>
          </div>
          <div className="text-[11px] text-gray-600 font-mono mb-4 px-1">v1.2.0-beta</div>
          
          <button
            type="button"
            onClick={() => {
              clearApiKey();
              clearActiveUserId();
              navigate("/login");
            }}
            className="w-full text-[13px] font-medium px-3 py-2.5 rounded-lg border border-[#222] bg-[#111] text-gray-300 hover:text-black hover:bg-white transition-colors flex items-center justify-center gap-2"
          >
            Sign Out
          </button>
        </div>
      </div>
    </aside>
  );
}
