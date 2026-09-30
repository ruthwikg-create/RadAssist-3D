"use client";

import { Activity, Calculator, CheckCircle2, Gauge, Info, Ruler, ShieldAlert, Sigma } from "lucide-react";
import type { CaseResult } from "../lib/types";

function format(value: number | null | undefined, digits = 2, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}${suffix}`;
}

function statusClass(status: string) {
  if (status === "PASS") return "ra-qc-pass";
  if (status === "FAIL") return "ra-qc-fail";
  return "ra-qc-review";
}

export default function MetricsPanel({ result }: { result: CaseResult }) {
  const dice = result.validation_benchmark.validation_dice;
  const quality = result.measurement_quality ?? {
    status: "REVIEW" as const,
    measurement_method: "QA metadata unavailable for this legacy case",
    voxel_volume_mm3: Number.NaN,
    labelmap_volume_cm3: result.volume_cm3,
    equivalent_diameter_mm: null,
    mask_fraction_pct: Number.NaN,
    connected_components: 0,
    largest_component_fraction_pct: null,
    touches_volume_boundary: false,
    surface_area_cm2: null,
    mesh_volume_cm3: null,
    volume_difference_pct: null,
    centroid_mm: null,
    intensity_domain: "Unavailable",
    hu_calibrated: false,
    rescale_slope: null,
    rescale_intercept: null,
    flags: ["This stored case predates the measurement-QA schema. Re-run the study for full QA/provenance."],
  };
  const model = result.model_provenance ?? {
    name: "Legacy case",
    architecture: "Unknown",
    dataset: "Unknown",
    checkpoint_loaded: false,
    checkpoint_sha256: null,
    preprocessing: {
      orientation: "Unknown",
      spacing_mm: [],
      hu_range: [],
      normalization: "Unknown",
    },
  };
  const h = result.hu_statistics;

  return (
    <aside className="space-y-3">
      <div className="glass rounded-2xl p-4">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Quantitative report</div>
            <div className="mt-1 text-xs text-slate-400">Physical-space measurements from the source image and labelmap.</div>
          </div>
          <Calculator size={17} className="text-teal-200" />
        </div>

        <div className="metric-grid rounded-2xl border border-white/10 bg-black/10 p-3">
          <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500">Target volume</div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-mono text-3xl font-medium tracking-tight text-white">{format(result.volume_cm3, 2)}</span>
            <span className="text-xs text-slate-500">cm³</span>
          </div>
          <div className="mt-2 text-[10px] text-slate-500">{result.voxel_count.toLocaleString()} segmented voxels · {format(quality.voxel_volume_mm3, 3)} mm³/voxel</div>
        </div>

        <div className="mt-2 ra-qc-grid">
          <div className="ra-qc-item"><div className="text-[8px] uppercase tracking-[0.12em] text-slate-600">Surface area</div><strong>{format(quality.surface_area_cm2, 2, " cm²")}</strong></div>
          <div className="ra-qc-item"><div className="text-[8px] uppercase tracking-[0.12em] text-slate-600">Mesh volume</div><strong>{format(quality.mesh_volume_cm3, 2, " cm³")}</strong></div>
          <div className="ra-qc-item"><div className="text-[8px] uppercase tracking-[0.12em] text-slate-600">Cross-check</div><strong>{format(quality.volume_difference_pct, 1, "%")}</strong></div>
          <div className="ra-qc-item"><div className="text-[8px] uppercase tracking-[0.12em] text-slate-600">Equivalent diameter</div><strong>{format(quality.equivalent_diameter_mm, 1, " mm")}</strong></div>
          <div className="ra-qc-item"><div className="text-[8px] uppercase tracking-[0.12em] text-slate-600">Mask coverage</div><strong>{format(quality.mask_fraction_pct, 3, "%")}</strong></div>
          <div className="ra-qc-item"><div className="text-[8px] uppercase tracking-[0.12em] text-slate-600">Components</div><strong>{quality.connected_components}</strong></div>
        </div>
      </div>

      <div className="glass rounded-2xl p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-white"><Activity size={15} className="text-teal-200" /> Intensity statistics</div>
          <span className={`rounded-full border px-2 py-1 text-[8px] font-bold tracking-[0.08em] ${result.modality === "MR" ? "border-violet-300/15 bg-violet-300/5 text-violet-200" : quality.hu_calibrated ? "border-teal-300/15 bg-teal-300/5 text-teal-200" : "border-amber-200/10 bg-amber-200/5 text-amber-100"}`}>
            {result.modality === "MR" ? "MR SIGNAL · UNCALIBRATED" : quality.hu_calibrated ? "HU VERIFIED" : "UNVERIFIED UNITS"}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {[
            ["Mean", h.mean_hu],
            ["Std dev", h.std_hu],
            ["Median", h.median_hu],
            ["Min", h.min_hu],
            ["Max", h.max_hu],
            ["P05–P95", h.p05_hu !== null && h.p95_hu !== null ? `${h.p05_hu.toFixed(0)} / ${h.p95_hu.toFixed(0)}` : null],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2.5">
              <div className="text-[9px] uppercase tracking-[0.12em] text-slate-600">{String(label)}</div>
              <div className="mt-1 font-mono text-sm text-slate-200">{typeof value === "string" ? value : format(value as number | null, 1)}</div>
            </div>
          ))}
        </div>
        <div className="mt-3 ra-provenance">
          <div className="ra-provenance-row"><span>Statistic domain</span><strong>{result.modality === "MR" ? "Source MR signal intensity" : quality.hu_calibrated ? "Hounsfield Units" : "Source intensity values"}</strong></div>
          <div className="ra-provenance-row"><span>Intensity domain</span><strong>{quality.intensity_domain}</strong></div>
          <div className="ra-provenance-row"><span>Measurement method</span><strong>{quality.measurement_method}</strong></div>
          {(quality.rescale_slope !== null || quality.rescale_intercept !== null) && (
            <div className="ra-provenance-row"><span>DICOM rescale</span><strong>{format(quality.rescale_slope, 4)} × SV {format(quality.rescale_intercept, 1, " + intercept")}</strong></div>
          )}
        </div>
      </div>

      <div className="glass rounded-2xl p-4">
        <div className="mb-3 flex items-center justify-between gap-3"><div className="flex items-center gap-2 text-xs font-semibold text-white"><Gauge size={15} className="text-amber-200" /> Model provenance</div><span className={`rounded-full border px-2 py-1 text-[8px] font-bold ${model.checkpoint_loaded ? "border-teal-300/15 bg-teal-300/5 text-teal-200" : "border-amber-200/10 bg-amber-200/5 text-amber-100"}`}>{model.checkpoint_loaded ? "CHECKPOINT LOADED" : "SYNTHETIC"}</span></div>
        <div className="ra-provenance">
          <div className="ra-provenance-row"><span>Model</span><strong>{model.name}</strong></div>
          <div className="ra-provenance-row"><span>Architecture</span><strong>{model.architecture}</strong></div>
          <div className="ra-provenance-row"><span>Training dataset</span><strong>{model.dataset}</strong></div>
          <div className="ra-provenance-row"><span>Held-out Dice</span><strong>{dice === null ? "Not available" : dice.toFixed(3)}</strong></div>
        </div>
        <div className="mt-3 flex items-start gap-2 rounded-xl border border-white/10 bg-white/[0.02] p-3 text-[9px] leading-4 text-slate-500">
          <Info size={13} className="mt-0.5 shrink-0 text-slate-400" /> The held-out Dice is a model-level benchmark. It is not a patient-specific accuracy estimate.
        </div>
      </div>

      <div className="glass rounded-2xl p-4">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-white"><Ruler size={15} className="text-sky-200" /> Acquisition & geometry</div>
        <div className="grid grid-cols-2 gap-2 text-[10px]">
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-2.5"><div className="text-slate-600">Source</div><div className="mt-1 font-mono text-slate-200">{result.source_type}</div></div>
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-2.5"><div className="text-slate-600">Modality</div><div className="mt-1 font-mono text-slate-200">{result.modality}</div></div>
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-2.5"><div className="text-slate-600">Spacing</div><div className="mt-1 font-mono text-slate-200">{result.original_spacing_mm.map((v) => v.toFixed(2)).join(" × ")} mm</div></div>
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-2.5"><div className="text-slate-600">Dimensions</div><div className="mt-1 font-mono text-slate-200">{result.original_dimensions.join(" × ")}</div></div>
        </div>
        {quality.centroid_mm && <div className="mt-2 ra-provenance"><div className="ra-provenance-row"><span>Centroid (physical xyz)</span><strong>{quality.centroid_mm.map((v) => v.toFixed(1)).join(" , ")} mm</strong></div></div>}
        <div className="mt-2 grid grid-cols-2 gap-2 text-[9px]">
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-2"><span className="text-slate-600">Largest component</span><strong className="mt-1 block text-slate-200">{format(quality.largest_component_fraction_pct, 1, "%")}</strong></div>
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-2"><span className="text-slate-600">Boundary contact</span><strong className="mt-1 block text-slate-200">{quality.touches_volume_boundary ? "Yes · review" : "No"}</strong></div>
        </div>
      </div>

      <div className="glass rounded-2xl p-4">
        <div className="mb-3 flex items-center justify-between gap-3"><div className="flex items-center gap-2 text-xs font-semibold text-white"><CheckCircle2 size={15} className={statusClass(quality.status)} /> Output QA</div><span className={`text-[9px] font-bold ${statusClass(quality.status)}`}>{quality.status}</span></div>
        <div className="space-y-2">
          {quality.flags.length === 0 ? <div className="flex items-start gap-2 rounded-xl border border-emerald-300/10 bg-emerald-300/[0.035] p-3 text-[9px] leading-4 text-emerald-100"><CheckCircle2 size={13} className="mt-0.5 shrink-0" /> No automated measurement-QA flags were raised for this case.</div> : quality.flags.map((flag) => <div key={flag} className="ra-flag"><ShieldAlert size={12} className="mt-0.5 shrink-0" />{flag}</div>)}
        </div>
      </div>

      <div className="glass rounded-2xl p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-white"><ShieldAlert size={15} className="text-sky-200" /> Structured QA</div>
          <span className={`text-[9px] font-bold ${statusClass(quality.status)}`}>{quality.status}</span>
        </div>
        <div className="grid grid-cols-2 gap-2 text-[9px]">
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-2"><span className="text-slate-600">Result schema</span><strong className="mt-1 block text-slate-200">radassist-result-1.0</strong></div>
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-2"><span className="text-slate-600">Patient accuracy</span><strong className="mt-1 block text-amber-100">Not established</strong></div>
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-2"><span className="text-slate-600">Measurement uncertainty</span><strong className="mt-1 block text-amber-100">Not estimated</strong></div>
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-2"><span className="text-slate-600">DICOM result architecture</span><strong className="mt-1 block text-slate-200">SEG / SR compatible</strong></div>
        </div>
      </div>

      {result.warnings.length > 0 && (
        <div className="glass rounded-2xl border-amber-200/10 p-4">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-amber-100"><ShieldAlert size={15} /> Review notes</div>
          <div className="space-y-2 text-[10px] leading-4 text-slate-400">
            {result.warnings.map((warning) => <div key={warning}>{warning}</div>)}
          </div>
        </div>
      )}

      <div className="glass rounded-2xl p-4 text-[10px] text-slate-500">
        <div className="mb-1 flex items-center gap-2 text-slate-400"><Sigma size={13} /> Processing</div>
        <div>{result.processing_seconds.toFixed(2)} s · mesh step {result.mesh_step_size} · QA {quality.status}</div>
      </div>
    </aside>
  );
}
