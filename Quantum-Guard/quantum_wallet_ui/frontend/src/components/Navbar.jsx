import { NavLink } from 'react-router-dom';

export default function Navbar() {
    const linkClass = ({ isActive }) =>
        `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${isActive
            ? 'bg-indigo-600 text-white shadow-md'
            : 'text-gray-300 hover:bg-gray-700 hover:text-white'
        }`;

    return (
        <nav className="bg-gray-900 border-b border-gray-800 sticky top-0 z-50">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="flex items-center justify-between h-16">
                    {/* Logo */}
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-indigo-500 rounded-lg flex items-center justify-center">
                            <span className="text-white font-bold text-sm">QG</span>
                        </div>
                        <span className="text-white font-semibold text-lg tracking-tight">
                            QuantumGuard
                        </span>
                        <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
                            v0.1.0
                        </span>
                    </div>

                    {/* Nav links */}
                    <div className="flex items-center gap-2">
                        <NavLink to="/" className={linkClass}>
                            Dashboard
                        </NavLink>
                        <NavLink to="/wallet" className={linkClass}>
                            Wallet
                        </NavLink>
                        <NavLink to="/transactions" className={linkClass}>
                            Transactions
                        </NavLink>
                        <NavLink to="/history" className={linkClass}>
                            History
                        </NavLink>
                        <NavLink to="/prover" className={linkClass}>
                            Prover
                        </NavLink>
                    </div>
                </div>
            </div>
        </nav>
    );
}
