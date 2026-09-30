"use client";

import { ArrowDown, ArrowUp, GitCompare, Minus } from "lucide-react";
import type { CaseResult } from "../lib/types";

function delta(current: number, previous: number) {
  if (!Number.isFinite(current) || !Number.isFinite(previous)) return null;
  return current - previous;
}

export default function CaseComparisonPanel({
  current,
  previous,
}: {
  current: CaseResult;
  previous: CaseResult;
}) {
  const volumeDelta = delta(current.volume_cm3, previous.volume_cm3);
  const pct = previous.volume_cm3 > 0 && volumeDelta !== null
    ? (volumeDelta / previous.volume_cm3) * 100
    : null;

  const Icon = volumeDelta === null || Math.abs(volumeDelta) < 1e-9
    ? Minus
    : volumeDelta > 0
      ? ArrowUp
      : ArrowDown;

  const qaCurrent = current.measurement_quality?.status ?? "REVIEW";
  const qaPrevious = previous.measurement_quality?.status ?? "REVIEW";

  return (
    <div className="ra-compare-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="ra-section-label">Longitudinal comparison</div>
          <div className="mt-1 text-[11px] font-semibold text-slate-200">
            Current case vs previous compatible study
          </div>
        </div>
        <GitCompare size={15} className="text-sky-300" />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
          <div className="text-[8px] uppercase tracking-[0.12em] text-slate-600">Current</div>
          <div className="mt-1 truncate font-mono text-[9px] text-slate-300">{current.request_id}</div>
          <div className="mt-2 font-mono text-xl text-white">{current.volume_cm3.toFixed(2)} <span className="text-[9px] text-slate-500">cm³</span></div>
          <div className="mt-1 text-[8px] text-slate-600">QA {qaCurrent}</div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
          <div className="text-[8px] uppercase tracking-[0.12em] text-slate-600">Previous</div>
          <div className="mt-1 truncate font-mono text-[9px] text-slate-300">{previous.request_id}</div>
          <div className="mt-2 font-mono text-xl text-white">{previous.volume_cm3.toFixed(2)} <span className="text-[9px] text-slate-500">cm³</span></div>
          <div className="mt-1 text-[8px] text-slate-600">QA {qaPrevious}</div>
        </div>
      </div>

      <div className="mt-2 grid grid-cols-3 gap-2">
        <div className="rounded-lg border border-white/10 bg-black/10 p-2">
          <div className="text-[8px] text-slate-600">Δ volume</div>
          <div className="mt-1 flex items-center gap-1 font-mono text-[10px] text-slate-200">
            <Icon size={12} /> {volumeDelta === null ? "—" : `${volumeDelta.toFixed(2)} cm³`}
          </div>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/10 p-2">
          <div className="text-[8px] text-slate-600">Relative change</div>
          <div className="mt-1 font-mono text-[10px] text-slate-200">{pct === null ? "—" : `${pct.toFixed(2)}%`}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/10 p-2">
          <div className="text-[8px] text-slate-600">Geometry</div>
          <div className="mt-1 font-mono text-[9px] text-slate-200">
            {current.original_dimensions.join("×")} vs {previous.original_dimensions.join("×")}
          </div>
        </div>
      </div>

      <div className="mt-2 text-[8px] leading-4 text-slate-600">
        This is a descriptive case-to-case comparison. It is not a clinical longitudinal interpretation and does not establish biological change.
      </div>
    </div>
  );
}
