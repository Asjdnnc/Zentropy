import React from "react";

export default function Card({
  children,
  className = "",
  variant = "default",
  title,
}) {
  const baseStyles = "glass-panel rounded-xl p-6 transition-all duration-300";

  const variants = {
    default: "hover:bg-white/5",
    neon: "neon-border-cyan hover:shadow-[0_0_15px_rgba(0,243,255,0.2)]",
    purple:
      "border border-neon-purple/30 hover:shadow-[0_0_15px_rgba(188,19,254,0.2)]",
  };

  return (
    <div
      className={`${baseStyles} ${variants[variant] || variants.default} ${className}`}
    >
      {title && (
        <h3 className="text-lg font-orbitron font-medium text-gray-200 mb-4 flex items-center gap-2">
          {title}
        </h3>
      )}
      {children}
    </div>
  );
}
