"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default class ViewerErrorBoundary extends Component<
  { label: string; children: ReactNode },
  { hasError: boolean; message: string }
> {
  state = { hasError: false, message: "" };

  static getDerivedStateFromError(error: unknown) {
    return {
      hasError: true,
      message: error instanceof Error ? error.message : "The viewer encountered an unexpected error.",
    };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error(`RadAssist ${this.props.label} viewer error`, error, info);
  }

  handleRetry = () => {
    this.setState({ hasError: false, message: "" });
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <section className="grid min-h-[320px] place-items-center rounded-2xl border border-rose-300/10 bg-[#070c10] p-6 text-center">
        <div className="max-w-md">
          <div className="mx-auto grid size-12 place-items-center rounded-2xl border border-rose-300/15 bg-rose-300/5 text-rose-200">
            <AlertTriangle size={20} />
          </div>
          <div className="mt-4 text-[10px] font-bold uppercase tracking-[0.16em] text-rose-200">{this.props.label} viewer</div>
          <div className="mt-2 font-heading text-lg font-semibold text-white">Viewer recovered outside the main workspace.</div>
          <div className="mt-2 text-[11px] leading-5 text-slate-500">{this.state.message}</div>
          <button type="button" onClick={this.handleRetry} className="mt-5 inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 text-[10px] font-bold text-slate-200 transition hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-teal-300/40">
            <RefreshCw size={14} /> Retry viewer
          </button>
        </div>
      </section>
    );
  }
}
