import React from "react";

export default function Button({
  children,
  onClick,
  variant = "primary",
  className = "",
  ...props
}) {
  const baseStyles =
    "relative px-6 py-2 pb-2 font-orbitron font-bold uppercase tracking-wider transition-all duration-300 transform hover:-translate-y-0.5 active:translate-y-0 clip-path-slant";

  // Custom clip-path for angled corners
  // logical CSS or SVG clip-path can be added in global CSS or inline style if needed,
  // but for now we'll simulate it with borders or just standard rounding if clip-path is complex in Tailwind 4 without config.
  // We'll stick to rounded-lg for simplicity unless we add custom CSS.
  // Updated plan: Use a cool gradient background and glow.

  const variants = {
    primary:
      "bg-gradient-to-r from-cyan-600 to-blue-600 text-white hover:shadow-[0_0_20px_rgba(0,243,255,0.4)] hover:brightness-110 rounded-lg",
    secondary:
      "bg-gray-800 border border-gray-600 text-gray-300 hover:text-white hover:border-gray-400 hover:bg-gray-750 rounded-lg",
    danger:
      "bg-red-900/50 border border-red-500/50 text-red-200 hover:bg-red-900/80 hover:shadow-[0_0_15px_rgba(255,0,0,0.3)] rounded-lg",
    neon: "bg-transparent border border-neon-cyan text-neon-cyan hover:bg-neon-cyan/10 hover:shadow-[0_0_15px_rgba(0,243,255,0.4)] rounded-lg",
  };

  return (
    <button
      onClick={onClick}
      className={`${baseStyles} ${variants[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
