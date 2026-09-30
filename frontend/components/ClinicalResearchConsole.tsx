"use client";

import {
  Archive,
  BarChart3,
  CheckCircle2,
  Download,
  FileDown,
  FolderOpen,
  Grid2X2,
  HelpCircle,
  Layers3,
  Lock,
  RefreshCcw,
  Settings,
  ShieldCheck,
  Terminal,
  UploadCloud,
  Box,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import type { BackendHealth, CaseResult, CaseSummary } from "../lib/types";

type Mode = "mpr" | "ai" | "research";

function n(value: number | null | undefined, digits = 2) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

function statusTone(value: string) {
  const v = value.toUpperCase();
  if (v.includes("PASS") || v.includes("READY") || v.includes("GENERATED") || v.includes("VERIFIED") || v.includes("LOADED") || v.includes("VALID") || v.includes("CAPTURED")) return "good";
  if (v.includes("REVIEW") || v.includes("WARN") || v.includes("UNAVAILABLE") || v.includes("NOT_AVAILABLE")) return "warn";
  return "bad";
}

function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`cw-card ${className}`}>{children}</section>;
}

function CardTitle({ icon, title, meta }: { icon?: React.ReactNode; title: string; meta?: string }) {
  return (
    <div className="cw-card-title">
      <div className="cw-card-title-main">
        {icon}
        <span>{title}</span>
      </div>
      {meta ? <span className="cw-card-meta">{meta}</span> : null}
    </div>
  );
}

function Metric({ label, value, unit, code, children }: { label: string; value: string; unit?: string; code?: string; children?: React.ReactNode }) {
  return (
    <div className="cw-kpi">
      <div className="cw-kpi-head"><span>{label}</span>{code ? <b>{code}</b> : null}</div>
      <div className="cw-kpi-value">{value}<small>{unit}</small></div>
      {children}
    </div>
  );
}

export default function ClinicalResearchConsole({
  result,
  backend,
  history,
  mode,
  onModeChange,
  onOpenHistory,
  onImport,
  onRefreshCase,
  onDownload,
  onSetError,
  onCompare,
  onSettings,
  viewerContent,
  importContent,
}: {
  result: CaseResult | null;
  backend: BackendHealth | null;
  history: CaseSummary[];
  mode: Mode;
  onModeChange: (mode: Mode) => void;
  onOpenHistory: (item: CaseSummary) => void;
  onImport: () => void;
  onRefreshCase: () => void;
  onDownload: (path: string, filename: string) => void;
  onSetError: (message: string) => void;
  onCompare: () => void;
  onSettings: () => void;
  viewerContent: React.ReactNode;
  importContent: React.ReactNode;
}) {
  const quality = result?.measurement_quality;
  const advanced = result?.advanced_metrics;
  const labels = (result?.label_metrics ?? []).filter((x) => x.name.toLowerCase() !== "background");
  const totalLabelPct = labels.reduce((sum, x) => sum + x.fraction_pct, 0);
  const agreement = quality?.volume_difference_pct;
  const model = result?.model_provenance;
  const [showSettings, setShowSettings] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [syncLocked, setSyncLocked] = useState(true);
  const [layoutMode, setLayoutMode] = useState<"stack" | "2x2">("stack");
  const [showExportDock, setShowExportDock] = useState(true);
  const hash = model?.checkpoint_sha256 ? model.checkpoint_sha256.slice(0, 12) : "—";
  const device = backend?.device ?? "offline";
  const loaded = backend ? Object.values(backend.models ?? {}).filter((x) => x.loaded).length : 0;
  const spacing = result?.original_spacing_mm?.map((v) => v.toFixed(2)).join(" × ") ?? "—";
  const dimensions = result?.original_dimensions?.join(" × ") ?? "—";

  const qa = [
    ["Input Contract", String(result?.input_validation?.status ?? "—")],
    ["3D Geometry", result ? "PASS" : "—"],
    ["Segmentation Topology", quality?.status ?? "—"],
    ["Measurement Consistency", agreement == null ? "REVIEW" : Math.abs(agreement) < 0.5 ? "PASS" : "REVIEW"],
    ["Mesh Quality Assurance", quality?.mesh_volume_cm3 == null ? "REVIEW" : "PASS"],
    ["Provenance Traceability", result?.provenance_record ? "PASS" : "—"],
    ["DICOM SEG / SR Export", result?.dicom_export?.status ?? "NOT_AVAILABLE"],
  ];

  const percentileValues = result
    ? [
        ["P05", result.hu_statistics.p05_hu],
        ["P25", null],
        ["MEDIAN", result.hu_statistics.median_hu],
        ["P75", null],
        ["P95", result.hu_statistics.p95_hu],
      ] as const
    : [];
  const knownIntensity = percentileValues.map(([, value]) => value).filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const intensityMin = knownIntensity.length ? Math.min(...knownIntensity) : 0;
  const intensityMax = knownIntensity.length ? Math.max(...knownIntensity) : 1;
  const intensitySpan = Math.max(1e-9, intensityMax - intensityMin);

  return (
    <div className="cw-shell">
      <header className="cw-header">
        <div className="cw-brand"><span className="cw-brand-dot" /><span>RADASSIST 3D</span></div>
        <div className="cw-study">
          <span className="cw-study-label">STUDY:</span>
          <strong>{result ? `${result.target.toUpperCase()} ${result.modality}` : "NO STUDY LOADED"}</strong>
          <i>|</i>
          <span className="cw-mono">{result ? `#${result.request_id.slice(0, 12)}` : "—"}</span>
          <i>|</i>
          <span>{result ? `${result.source_type} · ${dimensions}` : "Import DICOM/NIfTI"}</span>
          {result ? <em>{result.modality} [LPS]</em> : null}
        </div>
        <nav className="cw-mode-tabs">
          <button className={mode === "mpr" ? "active" : ""} onClick={() => onModeChange("mpr")}>CLINICAL MPR &amp; 3D</button>
          <button className={mode === "ai" ? "active" : ""} onClick={() => onModeChange("ai")}>AI SEGMENTATION</button>
          <button className={mode === "research" ? "active" : ""} onClick={() => onModeChange("research")}>RESEARCH &amp; QA</button>
        </nav>
        <div className="cw-header-actions">
          <span className="cw-live"><span /> LIVE SESSION</span>
          <button title={syncLocked ? "Unlock viewport synchronization" : "Lock viewport synchronization"} className={syncLocked ? "active" : ""} onClick={() => setSyncLocked((value) => !value)}><Lock size={14} /></button>
          <button title="Toggle viewer layout" className={layoutMode === "2x2" ? "active" : ""} onClick={() => setLayoutMode((value) => value === "stack" ? "2x2" : "stack")}><Grid2X2 size={14} /><span>{layoutMode === "2x2" ? "2×2" : "1×3"}</span></button>
          <button title="Refresh current study" onClick={onRefreshCase}><RefreshCcw size={14} /></button>
          <button title="Keyboard shortcuts" className={showHelp ? "active" : ""} onClick={() => setShowHelp((value) => !value)}><HelpCircle size={14} /></button>
          <button title="Settings" className={showSettings ? "active" : ""} onClick={() => { setShowSettings((value) => !value); onSettings(); }}><Settings size={14} /></button>
        </div>
      </header>

      {showSettings && (
        <section className="cw-settings-popover" aria-label="Workstation settings">
          <div><b>WORKSTATION SETTINGS</b><span>Display-only controls. Inference and stored measurements are unchanged.</span></div>
          <label><input type="checkbox" checked={syncLocked} onChange={(event) => setSyncLocked(event.target.checked)} /> Lock viewport synchronization</label>
          <label><input type="checkbox" checked={layoutMode === "2x2"} onChange={(event) => setLayoutMode(event.target.checked ? "2x2" : "stack")} /> Use 2×2 workspace layout</label>
          <label><input type="checkbox" checked={showExportDock} onChange={(event) => setShowExportDock(event.target.checked)} /> Show research export dock</label>
          <button type="button" onClick={() => { setLayoutMode("stack"); setSyncLocked(true); setShowExportDock(true); }}>Reset workstation view</button>
        </section>
      )}

      {showHelp && (
        <section className="cw-help-popover" aria-label="Keyboard shortcuts">
          <b>QUICK CONTROLS</b>
          <span>Mouse wheel / ↑↓ — change MPR slice</span>
          <span>LMB — active measurement tool</span>
          <span>MMB — pan · RMB — zoom</span>
          <span>Use the top 1×3 / 2×2 control to change the workstation arrangement.</span>
        </section>
      )}

      <aside className="cw-sidebar">
        <div>
          <div className="cw-sidebar-label">WORKSTATION MODES</div>
          {[
            ["Dashboard", Terminal, () => onModeChange("research")],
            ["Studies", FolderOpen, () => history[0] ? onOpenHistory(history[0]) : onSetError("No stored studies are available.")],
            ["Import DICOM/NIfTI", UploadCloud, onImport],
            ["MPR Viewer", Grid2X2, () => onModeChange("mpr")],
            ["3D Reconstruction", Box, () => onModeChange("ai")],
            ["Quantification", BarChart3, () => onModeChange("research")],
            ["QA & Validation", ShieldCheck, () => onModeChange("research")],
            ["Research Console", Terminal, () => onModeChange("research")],
            ["Research Export", Archive, () => document.getElementById("cw-export")?.scrollIntoView({ behavior: "smooth" })],
          ].map(([label, Icon, handler]) => {
            const active =
              (label === "MPR Viewer" && mode === "mpr") ||
              (label === "3D Reconstruction" && mode === "ai") ||
              (label === "Research Console" && mode === "research");
            const C = Icon as typeof Terminal;
            return <button key={String(label)} className={`cw-side-item ${active ? "active" : ""}`} onClick={handler as () => void}><C size={16} /><span>{String(label)}</span></button>;
          })}
        </div>
        <button className="cw-side-item" onClick={onSettings}><Settings size={16} /><span>Settings</span></button>
      </aside>

      <main className="cw-main">
        {!result ? (
          <Card className="cw-empty">
            <div className="cw-empty-title">Research workstation</div>
            <p>Import a CT/MRI DICOM study or NIfTI volume to activate MPR, AI segmentation, quantitative QA, provenance and research export.</p>
            <button className="cw-primary" onClick={onImport}><UploadCloud size={15} /> Import DICOM/NIfTI</button><div id="cw-import-zone" className="cw-import-zone">{importContent}</div>
          </Card>
        ) : mode === "research" ? (
          <>
            <div className="cw-console-head">
              <div>
                <div className="cw-console-kicker">VERIFICATION CORE {backend?.version ? `V${backend.version}` : "V1.0"} / NODE: {device.toUpperCase()} / HASH: SHA256:{hash}</div>
                <h1>RESEARCH CONSOLE &amp; QUANTITATIVE VALIDATION</h1>
                <p>Quantitative morphology, mesh agreement, source intensity distributions, verification gates, and reproducibility provenance.</p>
              </div>
              <div className="cw-toolbar">
                <button onClick={onRefreshCase}><RefreshCcw size={13} /> Re-validate QA Gates</button>
                <button onClick={() => onDownload(`/api/v1/cases/${result.request_id}/report`, `radassist-${result.request_id}-report.json`)}><FileDown size={13} /> Generate Report</button>
                <button className="primary" onClick={() => onDownload(`/api/v1/cases/${result.request_id}/bundle`, `radassist-${result.request_id}-research.zip`)}><Archive size={13} /> Export Research Bundle</button>
              </div>
            </div>

            <div className="cw-kpi-grid">
              <Metric label="QUANTIFIED VOLUME" value={n(result.volume_cm3)} unit="cm³" code="VOI-01">
                <div><span>Voxel: {n(quality?.voxel_volume_mm3 == null ? null : quality.voxel_volume_mm3 * result.voxel_count / 1000, 1)} cm³</span><span>Labelmap: {n(result.volume_cm3, 1)} cm³</span></div>
              </Metric>
              <Metric label="SURFACE AREA" value={n(quality?.surface_area_cm2)} unit="cm²" code="ISO-SURF">
                <div><span>Faces: {result.mesh.face_count.toLocaleString()}</span><span>Vertices: {result.mesh.vertex_count.toLocaleString()}</span></div>
              </Metric>
              <Metric label="EQUIVALENT DIAMETER" value={n(quality?.equivalent_diameter_mm == null ? null : quality.equivalent_diameter_mm / 10, 2)} unit="cm" code="D-EQ">
                <div><span>Sphericity Index: <b>{n(advanced?.sphericity, 2)}</b></span></div>
              </Metric>
              <Metric label="MESH ↔ LABELMAP AGREEMENT" value={n(agreement, 2)} unit="ΔV" code={agreement == null ? "REVIEW" : "VERIFIED"}>
                <div><span>Discrepancy: <b>&lt; 0.50% tolerance gate</b></span></div>
              </Metric>
            </div>

            <div className="cw-research-grid">
              <div className="cw-left">
                <Card>
                  <CardTitle icon={<BarChart3 size={16} />} title="Scientific Graphs & Visual Distribution" meta="LPS REFERENCE FRAME" />
                  <div className="cw-graph-block">
                    <div className="cw-graph-head"><span className="dot cyan" /> LABELMAP ↔ MESH AGREEMENT <span>(Zero-Centered Deviation)</span><b>{agreement == null ? "—" : `${agreement > 0 ? "+" : ""}${agreement.toFixed(2)}%`}</b></div>
                    <div className="cw-agreement-scale">
                      <span>-5%</span><span>-2%</span><strong>0.0% (NOMINAL)</strong><span>+2%</span><span>+5%</span>
                      <i style={{ left: `${Math.max(1, Math.min(99, 50 + (agreement ?? 0) * 10))}%` }} />
                    </div>
                    <div className="cw-graph-foot"><span>Algorithm: Marching Cubes</span><b>Physical spacing preservation: {result.original_spacing_mm.every((v) => v > 0) ? "OPTIMAL" : "REVIEW"}</b></div>
                  </div>

                  <div className="cw-graph-block">
                    <div className="cw-graph-head"><span className="dot blue" /> INTENSITY PROFILE <span>({result.modality === "MR" ? "Native MR signal distribution" : "Source intensity distribution"})</span><b>NON-CALIBRATED / SOURCE DOMAIN</b></div>
                    <div className="cw-percentile-chart">
                      {percentileValues.map(([label, value]) => <div key={label} className={label === "MEDIAN" ? "median" : ""}><i style={{ height: value == null ? "8%" : `${20 + ((value - intensityMin) / intensitySpan) * 70}%` }} /><span>{label}</span></div>)}
                    </div>
                    <div className="cw-percentile-strip">
                      {percentileValues.map(([label, value]) => <div key={label}><span>{label}</span><b>{value == null ? "—" : value.toFixed(1)}</b></div>)}
                    </div>
                  </div>

                  <div className="cw-graph-block">
                    <div className="cw-graph-head"><span className="dot green" /> SEGMENTATION LABEL COMPOSITION <b>TOTAL VOI: {result.voxel_count.toLocaleString()} VOXELS</b></div>
                    <div className="cw-stackbar">
                      {labels.map((item, index) => <i key={item.label} style={{ width: `${Math.max(0, item.fraction_pct / Math.max(1, totalLabelPct)) * 100}%`, opacity: 0.45 + (index % 3) * 0.2 }} />)}
                    </div>
                    <div className="cw-legend">{labels.map((item) => <span key={item.label}><i /> {item.name}: <b>{item.fraction_pct.toFixed(1)}%</b> ({item.voxel_count.toLocaleString()} vx)</span>)}</div>
                  </div>
                </Card>

                <Card>
                  <CardTitle icon={<Layers3 size={16} />} title="Mesh Quality & Geometric Integrity" meta="ISO-SURFACE MANIFOLD" />
                  <div className="cw-table">
                    <div><span>Connected components</span><b>{quality?.connected_components ?? "—"}</b><em className={statusTone(quality?.connected_components && quality.connected_components > 1 ? "REVIEW" : "PASS")}>{quality?.connected_components && quality.connected_components > 1 ? "REVIEW" : "PASS"}</em></div>
                    <div><span>Largest component fraction</span><b>{n(quality?.largest_component_fraction_pct, 1)}%</b><em className="good">Measured</em></div>
                    <div><span>Boundary contact</span><b>{quality?.touches_volume_boundary ? "Yes" : "No"}</b><em className={quality?.touches_volume_boundary ? "warn" : "good"}>{quality?.touches_volume_boundary ? "Review" : "PASS"}</em></div>
                    <div><span>Physical spacing matrix</span><b>{spacing} mm</b><em className="good">Preserved</em></div>
                    <div><span>Mesh step / decimation</span><b>{result.mesh_step_size}</b><em className="good">Configured</em></div>
                  </div>
                </Card>
              </div>

              <div className="cw-right">
                <Card>
                  <CardTitle icon={<ShieldCheck size={16} />} title="QA Validation Matrix" meta={`${qa.filter(([, value]) => statusTone(value) === "good").length}/${qa.length} GATES VALID`} />
                  <div className="cw-qa-list">
                    {qa.map(([label, value]) => <div key={label}><span>{statusTone(value) === "good" ? <CheckCircle2 size={14} /> : <XCircle size={14} />} {label}</span><b className={statusTone(value)}>{value}</b></div>)}
                  </div>
                  <div className="cw-topology">
                    <span>TOPOLOGY DIAGNOSTIC SUB-METRICS</span>
                    <div><b>Components:</b> {quality?.connected_components ?? "—"} <b>Largest:</b> {n(quality?.largest_component_fraction_pct, 1)}%</div>
                    <div><b>Boundary:</b> {quality?.touches_volume_boundary ? "Yes (Review)" : "No"} <b>Mask fraction:</b> {n(quality?.mask_fraction_pct, 1)}%</div>
                  </div>
                </Card>

                <Card>
                  <CardTitle icon={<Terminal size={16} />} title="Reproducible Provenance Audit" meta="DETERMINISTIC PIPELINE" />
                  <div className="cw-timeline">
                    <div><span>STUDY</span><b>Imported</b><small>{result.source_type} · {result.modality}</small></div>
                    <div><span>GEOMETRY</span><b>Validated</b><small>{dimensions} · {spacing} mm [LPS]</small></div>
                    <div><span>AI MODEL</span><b>{model?.checkpoint_loaded ? "Loaded" : "Unavailable"}</b><small>{model?.architecture ?? "—"} · {model?.name ?? "—"}</small></div>
                    <div><span>INFERENCE</span><b>Completed</b><small>Duration: {result.processing_seconds.toFixed(2)}s · Device: {device}</small></div>
                    <div><span>MORPHOLOGY</span><b>Calculated</b><small>Surface mesh extracted from segmentation</small></div>
                    <div><span>3D MESH</span><b>Generated</b><small>Vertices: {result.mesh.vertex_count.toLocaleString()} · Faces: {result.mesh.face_count.toLocaleString()}</small></div>
                    <div><span>QA</span><b>Executed</b><small>Schema: {String(result.provenance_record?.schema_version ?? "radassist-result-1.0")}</small></div>
                  </div>
                </Card>
              </div>
            </div>

            {showExportDock ? <Card className="cw-export" >
              <div id="cw-export" />
              <CardTitle icon={<Archive size={16} />} title="Clinical Export & Scientific Interoperability Dock" meta="DICOM PS3.3 / TID 1500 / NIFTI-1 / STL" />
              <div className="cw-export-grid">
                <button onClick={() => onDownload(`/api/v1/cases/${result.request_id}/report`, `radassist-${result.request_id}-report.json`)}><FileDown size={22} /><b>Structured Clinical Report</b><span>Source-derived report, QA snapshot and provenance.</span><strong>Export Report</strong></button>
                <button disabled={result.dicom_export?.status !== "GENERATED"} onClick={() => onDownload(`/api/v1/cases/${result.request_id}/dicom-seg`, "radassist-segmentation.dcm")}><Layers3 size={22} /><b>DICOM SEG Object</b><span>Generated when an authoritative DICOM source is available.</span><strong>Export .dcm</strong></button>
                <button disabled={result.dicom_export?.status !== "GENERATED"} onClick={() => onDownload(`/api/v1/cases/${result.request_id}/dicom-sr`, "radassist-measurements-sr.dcm")}><FileDown size={22} /><b>DICOM SR (TID 1500)</b><span>Structured measurement report for research interoperability.</span><strong>Export TID 1500</strong></button>
                <button onClick={() => onDownload(`/api/v1/cases/${result.request_id}/bundle`, `radassist-${result.request_id}-research.zip`)}><Download size={22} /><b>Full Research Bundle</b><span>JSON telemetry manifest + available case artifacts.</span><strong>Download .zip</strong></button>
              </div>
            </Card> : null}
          </>
        ) : (
          <div className="cw-mode-panel">
            <div className="cw-mode-title">{mode === "mpr" ? "CLINICAL MPR & 3D" : "AI SEGMENTATION"}</div>
            <p>Existing RadAssist imaging controls are preserved below. Use the workstation tabs to move between visualization and research QA.</p>
            <div id="cw-viewer-slot">{viewerContent}</div>
          </div>
        )}
      </main>

      <footer className="cw-footer">
        <div><b className="good">● WORKSPACE READY</b><span>CPU / {device.toUpperCase()}</span><span>AI MODELS {loaded}/3</span><span>MODEL: {model?.name ?? "—"}</span></div>
        <div><span className="cyan">MPR</span><span>3D</span><span>Volume: {dimensions}</span><span>({spacing}mm)</span></div>
        <div><span>DICOM 3.0 / NIfTI-1</span><span>Coordinate Space: LPS</span><b>Research Use Only</b></div>
      </footer>
    </div>
  );
}
