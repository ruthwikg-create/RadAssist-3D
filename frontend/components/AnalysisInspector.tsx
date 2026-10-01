"use client";

import { useMemo, useState } from "react";
import { BrainCircuit, ChevronDown, ChevronUp, ShieldCheck, Timer, Database, Sparkles } from "lucide-react";
import type { CaseResult } from "@/lib/types";

function fmt(value: unknown, digits = 2) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

export default function AnalysisInspector({ result }: { result: CaseResult }) {
  const [advanced, setAdvanced] = useState(false);
  const [provenance, setProvenance] = useState(false);
  const model = result.model_provenance;
  const quality = result.measurement_quality;
  const validation = result.validation_benchmark;

  const explanation = useMemo(() => {
    const anatomy = result.target === "heart" ? "cardiac MRI" : result.target === "prostate" ? "prostate MRI" : "spleen CT";
    const structures = (result.label_metrics ?? [])
      .filter((item) => item.volume_cm3 > 0)
      .map((item) => item.name + " " + fmt(item.volume_cm3) + " cm³")
      .join(", ");
    return "Structured summary: " + anatomy + " segmentation produced " +
      (structures || fmt(result.volume_cm3) + " cm³ total foreground") +
      ". Measurement QA is " + (quality?.status ?? "REVIEW") +
      ". This is research/engineering output, not a diagnosis or patient-specific accuracy estimate.";
  }, [result, quality?.status]);

  return (
    <div className="space-y-3">
      <section className="ra-inspector-card p-3">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-cyan-300" />
          <div>
            <div className="ra-section-label">Structured AI assistance</div>
            <div className="mt-1 text-[10px] text-slate-500">Derived only from result fields</div>
          </div>
        </div>
        <p className="mt-3 text-[10px] leading-5 text-slate-300">{explanation}</p>
        <div className="mt-2 rounded-lg border border-amber-300/10 bg-amber-300/[0.03] p-2 text-[9px] leading-4 text-amber-100">
          No diagnosis, prognosis, or treatment recommendation is generated here.
        </div>
      </section>

      <section className="ra-inspector-card p-3">
        <div className="flex items-center gap-2">
          <ShieldCheck size={14} className="text-teal-300" />
          <div>
            <div className="ra-section-label">Quality control</div>
            <div className="mt-1 text-[10px] text-slate-500">Input → model → segmentation</div>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2 text-[9px]">
          <div className="rounded-lg border border-white/10 bg-white/[0.02] p-2"><span className="text-slate-600">Input</span><strong className="mt-1 block text-teal-200">{result.input_validation?.status === "PASS" ? "PASS" : "REVIEW"}</strong></div>
          <div className="rounded-lg border border-white/10 bg-white/[0.02] p-2"><span className="text-slate-600">Model</span><strong className="mt-1 block text-teal-200">{model?.checkpoint_loaded ? "LOADED" : "REVIEW"}</strong></div>
          <div className="rounded-lg border border-white/10 bg-white/[0.02] p-2"><span className="text-slate-600">Segmentation</span><strong className={\`mt-1 block \${quality?.status === "PASS" ? "text-teal-200" : quality?.status === "FAIL" ? "text-rose-200" : "text-amber-200"}\`}>{quality?.status ?? "REVIEW"}</strong></div>
        </div>
        {quality?.flags?.length ? <div className="mt-3 space-y-1">{quality.flags.map((flag) => <div key={flag} className="rounded-md border border-amber-300/10 bg-amber-300/[0.025] px-2 py-1.5 text-[8px] leading-4 text-amber-100">{flag}</div>)}</div> : null}
      </section>

      <section className="ra-inspector-card p-3">
        <button type="button" onClick={() => setAdvanced((v) => !v)} className="flex w-full items-center gap-2 text-left">
          <Database size={14} className="text-slate-400" /><span className="ra-section-label flex-1">Advanced measurements</span>
          {advanced ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
        {advanced && <div className="mt-3 grid grid-cols-2 gap-2 text-[9px]">
          <div><span className="text-slate-600">Voxel volume</span><strong className="block text-slate-200">{fmt(quality?.voxel_volume_mm3, 4)} mm³</strong></div>
          <div><span className="text-slate-600">Mesh difference</span><strong className="block text-slate-200">{fmt(quality?.volume_difference_pct)}%</strong></div>
          <div><span className="text-slate-600">Surface area</span><strong className="block text-slate-200">{fmt(quality?.surface_area_cm2)} cm²</strong></div>
          <div><span className="text-slate-600">Components</span><strong className="block text-slate-200">{quality?.connected_components ?? "—"}</strong></div>
          <div><span className="text-slate-600">Boundary contact</span><strong className="block text-slate-200">{quality?.touches_volume_boundary ? "Yes" : "No"}</strong></div>
          <div><span className="text-slate-600">Processing</span><strong className="block text-slate-200">{fmt(result.processing_seconds)} s</strong></div>
          <div><span className="text-slate-600">Validation Dice</span><strong className="block text-slate-200">{validation.validation_dice == null ? "Not patient-specific" : fmt(validation.validation_dice)}</strong></div>
          <div><span className="text-slate-600">Intensity</span><strong className="block text-slate-200">{quality?.intensity_domain ?? "—"}</strong></div>
        </div>}
      </section>

      <section className="ra-inspector-card p-3">
        <button type="button" onClick={() => setProvenance((v) => !v)} className="flex w-full items-center gap-2 text-left">
          <BrainCircuit size={14} className="text-violet-300" /><span className="ra-section-label flex-1">Engineering provenance</span>
          {provenance ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
        {provenance && <div className="mt-3 space-y-2 text-[9px]">
          <div><span className="text-slate-600">Model</span><strong className="block text-slate-200">{model?.name ?? "—"}</strong></div>
          <div><span className="text-slate-600">Architecture</span><strong className="block text-slate-200">{model?.architecture ?? "—"}</strong></div>
          <div><span className="text-slate-600">Dataset</span><strong className="block text-slate-200">{model?.dataset ?? "—"}</strong></div>
          <div><span className="text-slate-600">Checkpoint SHA256</span><strong className="block break-all font-mono text-[8px] text-slate-300">{model?.checkpoint_sha256 ?? "—"}</strong></div>
          <div><span className="text-slate-600">Device</span><strong className="block text-slate-200">{String(model?.preprocessing?.device ?? "—")}</strong></div>
          <div><span className="text-slate-600">Input geometry</span><strong className="block text-slate-200">{result.original_dimensions.join(" × ")} · {result.original_spacing_mm.map((v) => v.toFixed(3)).join(" × ")} mm</strong></div>
        </div>}
      </section>

      <section className="ra-inspector-card p-3">
        <div className="flex items-center gap-2"><Timer size={14} className="text-slate-400" /><div><div className="ra-section-label">Performance</div><div className="mt-1 text-[10px] text-slate-500">End-to-end timing</div></div></div>
        <div className="mt-3 flex items-end justify-between"><span className="text-[9px] text-slate-600">Total processing time</span><strong className="font-mono text-lg text-slate-100">{fmt(result.processing_seconds)} s</strong></div>
        <div className="mt-2 text-[8px] leading-4 text-slate-600">Detailed stage timing is not fabricated; the backend currently records total request processing time.</div>
      </section>
    </div>
  );
}
