"use client";

import {
  Activity,
  BarChart3,
  Database,
  Gauge,
  Layers3,
  Ruler,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import type { CaseResult } from "../lib/types";

function finite(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function fmt(value: number | null | undefined, digits = 2, suffix = "") {
  const v = finite(value);
  return v === null ? "—" : `${v.toFixed(digits)}${suffix}`;
}

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value));
}

function Stat({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="ra-research-stat">
      <div className="ra-section-label">{label}</div>
      <strong>{value}</strong>
      {note ? <span>{note}</span> : null}
    </div>
  );
}

function CompositionChart({ result }: { result: CaseResult }) {
  const items = (result.label_metrics ?? [])
    .filter((item) => item.name.toLowerCase() !== "background")
    .map((item) => ({
      name: item.name,
      value: finite(item.fraction_pct) ?? 0,
    }));

  const max = Math.max(1, ...items.map((item) => item.value));

  return (
    <div className="ra-research-card">
      <div className="ra-research-card-head">
        <div>
          <div className="ra-section-label">Segmentation composition</div>
          <h3>Label contribution</h3>
          <p>Relative voxel contribution of each non-background label.</p>
        </div>
        <Layers3 size={16} />
      </div>
      <div className="ra-research-bars">
        {items.length ? items.map((item) => (
          <div key={item.name} className="ra-research-bar-row">
            <div className="ra-research-bar-label">
              <span>{item.name}</span>
              <strong>{item.value.toFixed(2)}%</strong>
            </div>
            <div className="ra-research-bar-track">
              <div
                className="ra-research-bar-fill"
                style={{ width: `${(item.value / max) * 100}%` }}
              />
            </div>
          </div>
        )) : (
          <div className="ra-research-empty">No label metrics are available for this case.</div>
        )}
      </div>
    </div>
  );
}

function MeasurementChart({ result }: { result: CaseResult }) {
  const quality = result.measurement_quality;
  const difference = finite(quality?.volume_difference_pct);
  const magnitude = Math.min(100, Math.abs(difference ?? 0));

  return (
    <div className="ra-research-card">
      <div className="ra-research-card-head">
        <div>
          <div className="ra-section-label">Measurement cross-check</div>
          <h3>Labelmap ↔ mesh agreement</h3>
          <p>Signed volume difference reported by the current QA pipeline.</p>
        </div>
        <Ruler size={16} />
      </div>
      <div className="ra-agreement">
        <div className="ra-agreement-axis">
          <span>−100%</span>
          <span>0%</span>
          <span>+100%</span>
        </div>
        <div className="ra-agreement-track">
          <div className="ra-agreement-zero" />
          {difference !== null ? (
            <div
              className={`ra-agreement-marker ${difference < 0 ? "negative" : "positive"}`}
              style={{
                left: `${50 + (difference / 2)}%`,
              }}
            />
          ) : null}
        </div>
        <div className="ra-agreement-readout">
          <strong>{fmt(difference, 2, "%")}</strong>
          <span>{difference === null ? "Cross-check unavailable" : `${magnitude.toFixed(1)} percentage points from zero`}</span>
        </div>
      </div>
    </div>
  );
}

function IntensityProfile({ result }: { result: CaseResult }) {
  const h = result.hu_statistics;
  const values = [
    ["P05", finite(h.p05_hu)],
    ["Min", finite(h.min_hu)],
    ["Median", finite(h.median_hu)],
    ["Mean", finite(h.mean_hu)],
    ["P95", finite(h.p95_hu)],
    ["Max", finite(h.max_hu)],
  ] as const;

  const known = values.map(([, value]) => value).filter((value): value is number => value !== null);
  const min = known.length ? Math.min(...known) : 0;
  const max = known.length ? Math.max(...known) : 1;
  const span = Math.max(1e-6, max - min);

  return (
    <div className="ra-research-card">
      <div className="ra-research-card-head">
        <div>
          <div className="ra-section-label">Intensity profile</div>
          <h3>{result.modality === "MR" ? "MR signal summary" : "Source intensity summary"}</h3>
          <p>Summary statistics only; no synthetic histogram is inferred from these values.</p>
        </div>
        <Activity size={16} />
      </div>
      <div className="ra-profile">
        {values.map(([label, value]) => (
          <div key={label} className="ra-profile-item">
            <span>{label}</span>
            <div className="ra-profile-track">
              <div
                className="ra-profile-point"
                style={{ left: `${value === null ? 0 : clamp01((value - min) / span) * 100}%` }}
              />
            </div>
            <strong>{value === null ? "—" : value.toFixed(1)}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ResearchAnalyticsPanel({
  result,
}: {
  result: CaseResult;
}) {
  const quality = result.measurement_quality;
  const advanced = result.advanced_metrics;
  const model = result.model_provenance;
  const validation = result.validation_benchmark;
  const exportStatus = result.dicom_export?.status ?? "NOT_AVAILABLE";
  const schemaValue = result.provenance_record?.schema_version;
  const schema = schemaValue == null ? "radassist-result-1.0" : String(schemaValue);

  return (
    <section id="research" className="ra-research-console ra-enter ra-enter-4">
      <div className="ra-research-header">
        <div>
          <div className="ra-section-label">Research console</div>
          <h2>Quantitative study intelligence</h2>
          <p>
            A research-facing view of the current result, keeping measured values,
            model metadata, QA state, and export state visibly separate.
          </p>
        </div>
        <div className="ra-research-live">
          <span />
          LIVE RESULT
        </div>
      </div>

      <div className="ra-research-kpis">
        <Stat label="Target volume" value={fmt(result.volume_cm3, 2, " cm³")} note="labelmap volume" />
        <Stat label="Surface area" value={fmt(quality?.surface_area_cm2, 2, " cm²")} note="mesh-derived" />
        <Stat label="Equivalent diameter" value={fmt(quality?.equivalent_diameter_mm, 1, " mm")} note="volume-equivalent sphere" />
        <Stat label="Sphericity" value={fmt(advanced?.sphericity, 4)} note="shape descriptor" />
        <Stat label="Processing" value={fmt(result.processing_seconds, 2, " s")} note={`mesh step ${result.mesh_step_size}`} />
        <Stat label="QA status" value={quality?.status ?? "REVIEW"} note={quality?.flags?.length ? `${quality.flags.length} review flag(s)` : "no automated flags"} />
      </div>

      <div className="ra-research-grid">
        <CompositionChart result={result} />
        <MeasurementChart result={result} />
        <IntensityProfile result={result} />

        <div className="ra-research-card">
          <div className="ra-research-card-head">
            <div>
              <div className="ra-section-label">Model & validation</div>
              <h3>Inference provenance</h3>
              <p>Model-level references are not patient-specific accuracy measurements.</p>
            </div>
            <Gauge size={16} />
          </div>
          <div className="ra-research-table">
            <div><span>Architecture</span><strong>{model?.architecture ?? "—"}</strong></div>
            <div><span>Dataset</span><strong>{model?.dataset ?? "—"}</strong></div>
            <div><span>Held-out Dice</span><strong>{finite(validation?.validation_dice)?.toFixed(3) ?? "—"}</strong></div>
            <div><span>Checkpoint</span><strong>{model?.checkpoint_loaded ? "Loaded" : "Unavailable"}</strong></div>
            <div><span>Dimensions</span><strong>{result.original_dimensions.join(" × ")}</strong></div>
            <div><span>Spacing</span><strong>{result.original_spacing_mm.map((v) => v.toFixed(2)).join(" × ")} mm</strong></div>
          </div>
        </div>
      </div>

      <div className="ra-research-bottom">
        <div className="ra-research-card">
          <div className="ra-research-card-head">
            <div>
              <div className="ra-section-label">QA matrix</div>
              <h3>Research integrity checks</h3>
            </div>
            <ShieldCheck size={16} />
          </div>
          <div className="ra-integrity-grid">
            <Stat label="Input contract" value={String(result.input_validation?.status ?? "—")} />
            <Stat label="Patient accuracy" value={String(result.uncertainty_status?.patient_specific_accuracy ?? "—")} />
            <Stat label="Measurement uncertainty" value={String(result.uncertainty_status?.measurement_uncertainty ?? "—")} />
            <Stat label="Result schema" value={schema} />
            <Stat label="DICOM export" value={exportStatus} />
            <Stat label="Provenance" value={result.provenance_record ? "Captured" : "—"} />
          </div>
        </div>

        <div className="ra-research-card">
          <div className="ra-research-card-head">
            <div>
              <div className="ra-section-label">Acquisition notes</div>
              <h3>Transformation trace</h3>
            </div>
            <Database size={16} />
          </div>
          {result.input_notes?.length ? (
            <div className="ra-note-list">
              {result.input_notes.map((note) => <div key={note}>{note}</div>)}
            </div>
          ) : (
            <div className="ra-research-empty">No input transformation notes were recorded.</div>
          )}
        </div>
      </div>

      <div className="ra-research-footer">
        <SlidersHorizontal size={13} />
        <span>Use the MPR, 3D, Quantification, and QA sections as synchronized views of the same stored result.</span>
      </div>
    </section>
  );
}
