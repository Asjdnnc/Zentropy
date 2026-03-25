import React from "react";

export default class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError() {
        return { hasError: true };
    }

    componentDidCatch(error, errorInfo) {
        console.error("[frontend] unhandled render error", error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="min-h-screen bg-bg-dark text-white flex items-center justify-center px-6">
                    <div className="glass-panel max-w-xl w-full p-8 border border-red-500/30 rounded-xl">
                        <h1 className="text-2xl font-orbitron text-red-300 mb-2">UI Error</h1>
                        <p className="text-sm text-gray-300 mb-4">
                            The dashboard hit an unexpected client-side error. Refresh the page to retry.
                        </p>
                        <button
                            type="button"
                            onClick={() => window.location.reload()}
                            className="px-4 py-2 rounded-lg bg-red-500/20 border border-red-400/30 text-red-200 hover:bg-red-500/30 transition-colors"
                        >
                            Reload
                        </button>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}
