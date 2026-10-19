/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { MaterialIcon } from './MaterialIcon.tsx';
import { clearAllData } from '../../services/storage.ts';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('App ErrorBoundary caught an unhandled exception:', error, errorInfo);
  }

  handleTryAgain = () => {
    this.setState({ hasError: false, error: null });
  };

  handleResetLocalData = () => {
    clearAllData();
    window.location.hash = '#operator-login';
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen w-full bg-[#030b14] flex justify-center items-center p-4">
          <div className="w-full max-w-[420px] rounded-3xl bg-[#0d1c2d] border border-red-500/40 p-6 flex flex-col items-center text-center shadow-2xl ring-1 ring-red-500/30">
            <div className="w-16 h-16 rounded-2xl bg-[#93000a]/30 border border-[#ff5451]/50 flex items-center justify-center text-[#ff5451] mb-3 shadow-[0_0_24px_rgba(255,84,81,0.3)]">
              <MaterialIcon name="error_outline" className="text-[36px]" />
            </div>

            <span className="font-mono text-[11px] font-extrabold uppercase tracking-widest text-[#ffdad6] mb-1">
              SYSTEM RECOVERY
            </span>

            <h1 className="font-sans text-lg font-extrabold text-white tracking-tight">
              Something went wrong
            </h1>

            <p className="font-body text-xs text-[#e4beba]/70 mt-2 max-w-[280px] leading-relaxed">
              An unexpected application error occurred. You can attempt to retry the current screen or reset stored local data to resolve data corruption.
            </p>

            {this.state.error?.message && (
              <div className="w-full mt-4 p-2.5 rounded-xl bg-[#010f1f] border border-[#273647] font-mono text-[11px] text-red-300 text-left overflow-x-auto max-h-24">
                {this.state.error.message}
              </div>
            )}

            <div className="flex flex-col gap-2.5 w-full mt-6">
              <button
                type="button"
                onClick={this.handleTryAgain}
                className="w-full min-h-[44px] py-2.5 px-4 rounded-full bg-[#4edea3] hover:bg-[#6ffbbe] text-[#003824] font-sans text-xs font-bold shadow-md active:scale-95 transition-all cursor-pointer"
              >
                Try Again
              </button>

              <button
                type="button"
                onClick={this.handleResetLocalData}
                className="w-full min-h-[44px] py-2.5 px-4 rounded-full bg-[#1c2b3c] hover:bg-red-950/60 border border-red-500/40 text-red-300 font-sans text-xs font-semibold active:scale-95 transition-all cursor-pointer"
              >
                Reset Local Data
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
