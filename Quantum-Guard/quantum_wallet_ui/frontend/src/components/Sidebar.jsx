import React from "react";
import { NavLink } from "react-router-dom";

export default function Sidebar() {
  const linkClass = ({ isActive }) =>
    `flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-300 ${isActive
      ? "bg-gradient-to-r from-indigo-900/50 to-purple-900/50 text-white border-l-2 border-neon-cyan shadow-[inset_0_0_20px_rgba(0,243,255,0.1)]"
      : "text-gray-400 hover:text-white hover:bg-white/5"
    }`;

  const navItems = [
    {
      to: "/",
      label: "Dashboard",
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"
          />
        </svg>
      ),
    },
    {
      to: "/wallet",
      label: "Create Wallet",
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 4v16m8-8H4"
          />
        </svg>
      ),
    },
    {
      to: "/send",
      label: "Send STRK",
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M13 10V3L4 14h7v7l9-11h-7z"
          />
        </svg>
      ),
    },
    {
      to: "/receive",
      label: "Receive",
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
          />
        </svg>
      ),
    },
    {
      to: "/history",
      label: "History",
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      ),
    },
    {
      to: "/prover",
      label: "Prover Status",
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      ),
    },
  ];

  return (
    <aside className="w-64 glass-panel border-r border-white/5 hidden md:flex flex-col h-screen fixed left-0 top-0 overflow-y-auto">
      <div className="p-6 flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
          <span className="font-orbitron font-bold text-white text-xl">Q</span>
        </div>
        <div>
          <h1 className="font-orbitron font-bold text-white tracking-wider text-sm">
            QUANTUM
          </h1>
          <h1 className="font-orbitron font-bold text-neon-cyan tracking-wider text-xs">
            GUARD
          </h1>
        </div>
      </div>

      <nav className="flex-1 px-4 py-6 space-y-2">
        <p className="px-4 text-xs font-semibold text-gray-500 uppercase tracking-widest mb-4">
          Menu
        </p>
        {navItems.map((item) => (
          <NavLink key={item.to} to={item.to} className={linkClass}>
            {item.icon}
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t border-white/5">
        <div className="bg-white/5 rounded-xl p-4">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-2 h-2 rounded-full bg-neon-green animate-pulse"></div>
            <span className="text-xs text-gray-400">System Online</span>
          </div>
          <div className="text-xs text-gray-500 font-mono">v0.1.0-beta</div>
        </div>
      </div>
    </aside>
  );
}
