import { Link } from "react-router-dom";

export default function Landing() {
    return (
        <div className="min-h-screen bg-black text-white font-sans flex flex-col selection:bg-blue-500 selection:text-white">
            
            {/* 1. Hero Section (100vh) */}
            <section className="relative w-full h-[100dvh] overflow-hidden flex flex-col border-b border-[#1a1a1a]">
                {/* 3D Spline Background Canvas */}
                <div className="absolute inset-0 z-0 flex items-center justify-center overflow-hidden bg-black">
                     <iframe 
                         src='https://my.spline.design/boxeshover-46uN5nKlQN0jgwPQ5s6Dib9i/'
                         frameBorder="0" 
                         width="100%" 
                         height="100%" 
                         className="w-full h-full pointer-events-auto border-none outline-none scale-[1.8] md:scale-[2.4] origin-center"
                     ></iframe>
                     
                     {/* Subtle bottom fade to seamlessly transition into the next black section */}
                     <div className="absolute bottom-0 left-0 w-full h-32 bg-gradient-to-t from-black to-transparent pointer-events-none"></div>
                </div>

                {/* UI Overlay In The Foreground */}
                <div className="relative z-10 flex flex-col h-full w-full pointer-events-none p-8 md:p-16 pb-12">
                    
                    {/* Top Navbar */}
                    <header className="flex items-center justify-between w-full pointer-events-auto">
                        <nav className="flex items-center gap-12">
                            <Link to="/" className="font-bold text-xl tracking-tight text-white flex items-center gap-3">
                                <div className="w-8 h-8 bg-white text-black flex items-center justify-center rounded-md font-extrabold text-[12px] tracking-tighter">Zen</div>
                                ZENTROPY
                            </Link>
                            <div className="hidden md:flex items-center gap-8 text-[13px] text-gray-400 font-medium tracking-wide">
                                <Link to="https://github.com/Asjdnnc/Zentropy" className="hover:text-white transition-colors">Github</Link>
                                <Link to="https://zentropy-docs.vercel.app" className="hover:text-white transition-colors">Docs</Link>
                                <Link to="https://openquantumsafe.org/liboqs/" className="hover:text-white transition-colors">Resources</Link>
                            </div>
                        </nav>
                        <Link to="/login" className="hidden sm:inline-flex px-7 py-3 rounded-full border border-gray-700 text-[13px] font-semibold text-gray-300 hover:text-white hover:border-white transition-colors">
                            Let's Talk!
                        </Link>
                    </header>

                    {/* Main Hero Typography */}
                    <main className="mt-[50vh] grid grid-cols-1 lg:grid-cols-2 w-full gap-8 items-end pointer-events-none">
                        
                        {/* Left Typography Block */}
                        <div className="flex flex-col md:mt-0 pointer-events-auto">
                            <h1 className="text-[54px] md:text-[82px] font-bold tracking-tighter mb-8 leading-[1.05] text-white">
                                We`re Building<br/>
                                Quantum Security
                            </h1>
                            <div className="flex flex-wrap items-center gap-4 text-[14px] tracking-[0.25em] text-gray-500 font-medium uppercase font-mono">
                                <span>Strk</span> <span className="text-gray-700">\</span>
                                <span>Liboqs</span> <span className="text-gray-700">\</span>
                                <span>Drand</span> <span className="text-gray-700">\</span>
                                <span>KYBER</span> <span className="text-gray-700">\</span>
                                <span>Dilithium</span>
                            </div>
                        </div>

                        {/* Right Action Block */}
                        <div className="flex flex-col lg:items-end text-left lg:text-left pointer-events-auto">
                            <p className="text-gray-400 text-[15px] max-w-sm mb-12 leading-relaxed font-medium">
                            Making a Q-Day proof<br/>
                            Crypto Wallet
                            </p>
                            
                            <div className="flex items-center gap-4">
                                <Link to="/" className="px-8 py-3.5 rounded-full border border-gray-700 text-[14px] font-medium text-gray-300 hover:bg-white hover:text-black transition-colors">
                                    Contact Us
                                </Link>
                                <Link to="/signup" className="flex items-center pl-7 pr-1.5 py-1.5 rounded-full border border-gray-700 text-[14px] font-medium hover:border-gray-400 transition-colors group">
                                    <span className="mr-6 text-gray-300 group-hover:text-white transition-colors">Get Started</span>
                                    <div className="w-10 h-10 rounded-full bg-[#00e1ff] flex items-center justify-center text-black group-hover:scale-105 transition-transform duration-300">
                                        <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                                        </svg>
                                    </div>
                                </Link>
                            </div>
                        </div>
                    </main>
                </div>
            </section>

            {/* 2. Features Section */}
            <section className="w-full bg-black py-24">
                <div className="max-w-7xl mx-auto px-6 md:px-12">
                    <div className="mb-16 md:mb-24 text-center md:text-left flex flex-col items-center md:items-start">
                        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[#333] bg-[#111] text-gray-300 text-[11px] font-mono mb-6 uppercase tracking-wider">
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></span>
                            Next Generation Custody
                        </div>
                        <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-5 leading-tight">
                            Post-Quantum Security,<br/>
                            <span className="text-gray-500">Built for Starknet.</span>
                        </h2>
                        <p className="text-gray-400 text-lg max-w-2xl leading-relaxed">
                            Quantum-Guard combines lattice-based cryptography with Starknet's architecture, ensuring your assets are mathematically immune to next-generation quantum threats while retaining zero-friction execution.
                        </p>
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {/* Feature 1 */}
                        <div className="bg-[#0a0a0a] border border-[#1a1a1a] p-8 rounded-[20px] hover:border-[#333] transition-colors group">
                            <div className="w-12 h-12 rounded-full bg-[#111] border border-[#222] flex items-center justify-center mb-6 text-gray-400 group-hover:text-blue-500 transition-colors">
                                <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg>
                            </div>
                            <h3 className="text-xl font-semibold mb-3 tracking-tight">PQC Resistance</h3>
                            <p className="text-gray-400 leading-relaxed text-[15px]">
                                Protected by ML-KEM lattice-based cryptography, completely neutralizing Shor's algorithm and all known future quantum decryption vectors.
                            </p>
                        </div>

                        {/* Feature 2 */}
                        <div className="bg-[#0a0a0a] border border-[#1a1a1a] p-8 rounded-[20px] hover:border-[#333] transition-colors group">
                            <div className="w-12 h-12 rounded-full bg-[#111] border border-[#222] flex items-center justify-center mb-6 text-gray-400 group-hover:text-blue-500 transition-colors">
                                <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                            </div>
                            <h3 className="text-xl font-semibold mb-3 tracking-tight">Cryptographic Co-Processor</h3>
                            <p className="text-gray-400 leading-relaxed text-[15px]">
Rust-based off-chain cryptographic co-processor handles heavy polynomial computations for ML-DSA-44 quantum-resistant signatures (~2.5KB).
Only a deterministic hash is committed on-chain, ensuring security, scalability, and efficiency.                            </p>
                        </div>

                        {/* Feature 3 */}
                        <div className="bg-[#0a0a0a] border border-[#1a1a1a] p-8 rounded-[20px] hover:border-[#333] transition-colors group">
                            <div className="w-12 h-12 rounded-full bg-[#111] border border-[#222] flex items-center justify-center mb-6 text-gray-400 group-hover:text-blue-500 transition-colors">
                                <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
                            </div>
                            <h3 className="text-xl font-semibold mb-3 tracking-tight">Smart Abstraction</h3>
                            <p className="text-gray-400 leading-relaxed text-[15px]">
                                Your wallet is a programmable contract. Implement custom daily limits, social recovery, and multi-signature security layers natively.
                            </p>
                        </div>
                    </div>
                </div>
            </section>

            {/* 3. Call to Action */}
            <section className="w-full bg-[#050505] py-24 relative border-t border-[#1a1a1a]">
                <div className="max-w-3xl mx-auto px-6 text-center">
                    <h2 className="text-3xl font-bold tracking-tight mb-6">Ready to upgrade your security?</h2>
                    <p className="text-gray-400 mb-10 text-lg">
                        Initialize your quantum-safe keypair and deploy your Starknet abstracted account in less than a minute.
                    </p>
                    <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                        <Link to="/signup" className="px-8 py-3.5 rounded-full bg-blue-600 text-white text-[15px] font-semibold hover:bg-blue-500 transition-colors w-full sm:w-auto shadow-lg shadow-blue-500/20">
                            Create New Account
                        </Link>
                        <Link to="/login" className="px-8 py-3.5 rounded-full bg-[#111] border border-[#222] text-white text-[15px] font-semibold hover:bg-[#1a1a1a] hover:text-white hover:border-[#333] transition-colors w-full sm:w-auto">
                            Login (API / Key)
                        </Link>
                    </div>
                </div>
            </section>

            {/* 4. Footer */}
            <footer className="w-full bg-black border-t border-[#1a1a1a] py-8">
                <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between text-sm text-gray-500">
                    <div className="flex items-center gap-3 mb-4 md:mb-0">
                        <div className="w-6 h-6 rounded-md bg-white flex items-center justify-center">
                           <span className="font-bold text-black text-[10px] tracking-tighter">Zen</span>
                        </div>
                        <span className="font-semibold text-gray-300 tracking-wide">Zentropy</span>
                    </div>
                    <div className="flex gap-8 font-medium">
                        
                        <Link to="https://zentropy-docs.vercel.app/" className="hover:text-white transition-colors">Documentation</Link>
                        <Link to="https://github.com/Asjdnnc/Zentropy" className="hover:text-white transition-colors">GitHub</Link>
                    </div>
                </div>
            </footer>

        </div>
    );
}
