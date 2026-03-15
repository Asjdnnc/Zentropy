import React from "react";

export default function StatusBadge({ status, label }) {
  const styles = {
    ready:
      "bg-green-500/10 text-green-400 border-green-500/20 shadow-[0_0_10px_rgba(74,222,128,0.1)]",
    healthy:
      "bg-green-500/10 text-green-400 border-green-500/20 shadow-[0_0_10px_rgba(74,222,128,0.1)]",
    warning:
      "bg-yellow-500/10 text-yellow-400 border-yellow-500/20 shadow-[0_0_10px_rgba(250,204,21,0.1)]",
    offline:
      "bg-red-500/10 text-red-400 border-red-500/20 shadow-[0_0_10px_rgba(248,113,113,0.1)]",
    pending: "bg-blue-500/10 text-blue-400 border-blue-500/20 animate-pulse",
    default: "bg-gray-500/10 text-gray-400 border-gray-500/20",
  };

  const currentStyle =
    styles[status] || styles[label?.toLowerCase()] || styles.default;
  const displayLabel = label || status;

  return (
    <span
      className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border ${currentStyle} backdrop-blur-sm transition-all duration-300`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full bg-current ${status === "pending" ? "animate-ping" : ""}`}
      />
      <span className="font-orbitron tracking-wide">{displayLabel}</span>
    </span>
  );
}
