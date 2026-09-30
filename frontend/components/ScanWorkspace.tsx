"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Check,
  Circle,
  Database,
  Download,
  FileDown,
  LoaderCircle,
  Microscope,
  RefreshCw,
  ScanLine,
  Server,
  ShieldCheck,
  Sparkles,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";

import Dropzone from "./Dropzone";
import CornerstoneMPRViewer from "./CornerstoneMPRViewer";
import DemoMPRViewer from "./DemoMPRViewer";
import Three3DMeshViewer from "./Three3DMeshViewer";
import MetricsPanel from "./MetricsPanel";
import AdvancedAnalyticsPanel from "./AdvancedAnalyticsPanel";
import ViewerErrorBoundary from "./ViewerErrorBoundary";

import type {
  BackendHealth,
  CaseResult,
  CaseSummary,
  ModelInfo,
} from "../lib/types";

import {
  API_BASE_URL,
  createAuthenticatedObjectUrl,
  caseBundleUrl,
  caseReportUrl,
  caseDicomSegUrl,
  caseDicomSrUrl,
  caseMaskUrl,
  createDemoCase,
  deleteCase,
  downloadApiFile,
  fetchHealth,
  getCase,
  listCases,
  segmentFiles,
} from "../lib/api";

type Target = "spleen" | "heart" | "prostate";

const TARGET_ORDER: Target[] = [
  "spleen",
  "heart",
  "prostate",
];

const FALLBACK_MODELS: Record<
  Target,
  ModelInfo
> = {
  spleen: {
    display_name: "Spleen",
    modality: "CT",
    description: "Spleen CT segmentation",
    labels: {
      "0": "background",
      "1": "spleen",
    },
    loaded: false,
    error: null,
  },

  heart: {
    display_name: "Heart",
    modality: "MR",
    description:
      "Cardiac MRI ventricular segmentation",
    labels: {
      "0": "background",
      "1": "LV blood pool",
      "2": "myocardium",
      "3": "RV blood pool",
    },
    loaded: false,
    error: null,
  },

  prostate: {
    display_name: "Prostate",
    modality: "MR",
    description:
      "Prostate MRI zonal segmentation",
    labels: {
      "0": "background",
      "1": "central gland",
      "2": "peripheral zone",
    },
    loaded: false,
    error: null,
  },
};

const steps = [
  ["ingest", "Import", "Acquire study"],
  ["preprocess", "Prepare", "Orient + normalize"],
  ["infer", "Segment", "Run selected AI model"],
  ["render", "Analyze", "MPR + 3D + metrics"],
] as const;

type Stage = (typeof steps)[number][0];

type BackendState = BackendHealth;

function formatDate(
  value:
    | string
    | null
    | undefined,
) {
  if (!value) return "";

  try {
    return new Intl.DateTimeFormat(
      undefined,
      {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      },
    ).format(new Date(value));
  } catch {
    return "";
  }
}

function StageRail({
  active,
  result,
}: {
  active: Stage;
  result: CaseResult | null;
}) {
  const activeIndex = Math.max(
    0,
    steps.findIndex(
      ([key]) => key === active,
    ),
  );

  return (
    <div
      className="ra-stage-rail"
      aria-label="Analysis workflow"
    >
      {steps.map(
        (
          [key, label, subtitle],
          index,
        ) => {
          const complete =
            Boolean(result) ||
            index < activeIndex;

          const current =
            !result &&
            index === activeIndex;

          return (
            <div
              key={key}
              className={`ra-stage ${
                current
                  ? "active"
                  : ""
              } ${
                complete
                  ? "done"
                  : ""
              } ra-enter ra-enter-${
                index + 1
              }`}
            >
              <div
                className="ra-stage-icon"
                aria-hidden="true"
              >
                {complete ? (
                  <Check size={13} />
                ) : current ? (
                  <LoaderCircle
                    size={13}
                    className="ra-pulse"
                  />
                ) : (
                  <Circle size={9} />
                )}
              </div>

              <div className="ra-stage-copy">
                <div className="ra-stage-label">
                  {label}
                </div>

                <div className="ra-stage-sub">
                  {subtitle}
                </div>
              </div>
            </div>
          );
        },
      )}
    </div>
  );
}

async function downloadArtifact(
  path: string,
  filename: string,
  setError: (
    message: string,
  ) => void,
) {
  try {
    await downloadApiFile(
      path,
      filename,
    );
  } catch (err) {
    setError(
      err instanceof Error
        ? err.message
        : "Download failed.",
    );
  }
}

function downloadJson(
  result: CaseResult,
) {
  const blob = new Blob(
    [
      JSON.stringify(
        result,
        null,
        2,
      ),
    ],
    {
      type: "application/json",
    },
  );

  const url =
    URL.createObjectURL(
      blob,
    );

  const anchor =
    document.createElement("a");

  anchor.href = url;
  anchor.download = `radassist-${result.request_id}.json`;

  document.body.appendChild(
    anchor,
  );

  anchor.click();
  anchor.remove();

  window.setTimeout(
    () =>
      URL.revokeObjectURL(
        url,
      ),
    1000,
  );
}

function targetLabel(
  target: Target,
) {
  switch (target) {
    case "heart":
      return "Heart MRI";

    case "prostate":
      return "Prostate MRI";

    default:
      return "Spleen CT";
  }
}

function targetDescription(
  target: Target,
) {
  switch (target) {
    case "heart":
      return "Ventricular segmentation · 3 structures";

    case "prostate":
      return "Zonal segmentation · central gland + peripheral zone";

    default:
      return "Spleen segmentation · CT";
  }
}

export default function ScanWorkspace() {
  const [files, setFiles] =
    useState<File[]>([]);

  const [selectedTarget, setSelectedTarget] =
    useState<Target>("spleen");

  const [stage, setStage] =
    useState<Stage>("ingest");

  const [progress, setProgress] =
    useState(0);

  const [working, setWorking] =
    useState(false);

  const [result, setResult] =
    useState<CaseResult | null>(null);

  const [history, setHistory] =
    useState<CaseSummary[]>([]);

  const [backend, setBackend] =
    useState<BackendState | null>(
      null,
    );

  const [error, setError] =
    useState<string | null>(
      null,
    );

  const [protectedVolumeUrl, setProtectedVolumeUrl] =
    useState<string | null>(null);

  const selectedModel =
    backend?.models?.[
      selectedTarget
    ] ??
    FALLBACK_MODELS[
      selectedTarget
    ];

  const selectedSummary =
    useMemo(() => {
      if (result) {
        return `${result.target.toUpperCase()} · ${result.modality}`;
      }

      if (!files.length) {
        return `${targetLabel(
          selectedTarget,
        )} · No study loaded`;
      }

      return files.length === 1
        ? files[0].name
        : `${files.length} DICOM instances`;
    }, [
      files,
      result,
      selectedTarget,
    ]);

  const stageMessage =
    useMemo(() => {
      if (progress >= 100) {
        return "Complete";
      }

      switch (stage) {
        case "ingest":
          return "Uploading study";

        case "preprocess":
          return `Preparing ${targetLabel(
            selectedTarget,
          )}`;

        case "infer":
          return `Running ${
            selectedModel.display_name
          } model`;

        default:
          return "Preparing visualization";
      }
    }, [
      progress,
      stage,
      selectedTarget,
      selectedModel,
    ]);

  useEffect(() => {
    let disposed = false;
    let objectUrl: string | null = null;

    if (!result || result.is_demo || !result.preview.volume_url) {
      setProtectedVolumeUrl(null);
      return () => {};
    }

    void (async () => {
      try {
        const url = await createAuthenticatedObjectUrl(result.preview.volume_url);
        objectUrl = url;
        if (!disposed) {
          setProtectedVolumeUrl(url);
        } else {
          URL.revokeObjectURL(url);
        }
      } catch (err) {
        if (!disposed) {
          setProtectedVolumeUrl(null);
          setError(
            err instanceof Error
              ? `Protected imaging volume could not be loaded: ${err.message}`
              : "Protected imaging volume could not be loaded.",
          );
        }
      }
    })();

    return () => {
      disposed = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setProtectedVolumeUrl(null);
    };
  }, [result]);

  useEffect(() => {
    void (async () => {
      try {
        const health =
          await fetchHealth();

        setBackend(health);
      } catch {
        setBackend(null);
      }

      try {
        setHistory(
          await listCases(),
        );
      } catch {
        setHistory([]);
      }
    })();
  }, []);

  function handleTargetChange(
    target: Target,
  ) {
    if (working) return;

    setSelectedTarget(
      target,
    );

    setError(null);

    setResult(null);
    setStage("ingest");
    setProgress(0);
  }

  async function analyze() {
    if (!files.length) {
      setError(
        "Select a NIfTI volume or DICOM study first.",
      );
      return;
    }

    if (!selectedModel.loaded) {
      setError(
        `${selectedModel.display_name} model is not currently available.`,
      );
      return;
    }

    setWorking(true);
    setError(null);
    setResult(null);
    setStage("ingest");
    setProgress(0);

    try {
      const response =
        await segmentFiles(
          selectedTarget,
          files,
          (value: number) => {
            if (value >= 100) {
              setProgress(99);
              setStage(
                "preprocess",
              );
            } else {
              setProgress(
                Math.min(
                  98,
                  value,
                ),
              );
            }
          },
        );

      setStage("preprocess");

      await new Promise(
        (resolve) =>
          setTimeout(
            resolve,
            120,
          ),
      );

      setStage("infer");

      await new Promise(
        (resolve) =>
          setTimeout(
            resolve,
            120,
          ),
      );

      setStage("render");
      setResult(response);
      setProgress(100);

      if (
        response.persisted !==
        false
      ) {
        setHistory(
          (current) => [
            {
              case_id:
                response.request_id,
              target:
                response.target,
              source_type:
                response.source_type,
              modality:
                response.modality,
              volume_cm3:
                response.volume_cm3,
              stored_at:
                response.stored_at ??
                new Date().toISOString(),
              is_demo:
                response.is_demo,
            },
            ...current.filter(
              (item) =>
                item.case_id !==
                response.request_id,
            ),
          ].slice(0, 12),
        );
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Analysis failed.",
      );

      setStage("ingest");
      setProgress(0);
    } finally {
      setWorking(false);
    }
  }

  async function runDemo() {
    setWorking(true);
    setError(null);
    setResult(null);
    setStage("infer");
    setProgress(18);

    try {
      const demo =
        await createDemoCase();

      setStage("render");
      setProgress(100);
      setResult(demo);
      setFiles([]);

      if (
        demo.persisted !==
        false
      ) {
        setHistory(
          (current) => [
            {
              case_id:
                demo.request_id,
              target:
                demo.target,
              source_type:
                demo.source_type,
              modality:
                demo.modality,
              volume_cm3:
                demo.volume_cm3,
              stored_at:
                demo.stored_at ??
                new Date().toISOString(),
              is_demo: true,
            },
            ...current.filter(
              (item) =>
                item.case_id !==
                demo.request_id,
            ),
          ].slice(0, 12),
        );
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Synthetic demo failed.",
      );
    } finally {
      setWorking(false);
    }
  }

  async function openHistory(
    item: CaseSummary,
  ) {
    setWorking(true);
    setError(null);

    try {
      const body =
        await getCase(
          item.case_id,
        );

      setResult(body);
      setFiles([]);

      if (
        body.target ===
          "spleen" ||
        body.target ===
          "heart" ||
        body.target ===
          "prostate"
      ) {
        setSelectedTarget(
          body.target,
        );
      }

      setStage("render");
      setProgress(100);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to reopen case.",
      );
    } finally {
      setWorking(false);
    }
  }

  async function removeCurrent() {
    if (!result) return;

    try {
      if (
        result.persisted !==
        false
      ) {
        await deleteCase(
          result.request_id,
        );
      }

      setHistory(
        (items) =>
          items.filter(
            (item) =>
              item.case_id !==
              result.request_id,
          ),
      );

      setResult(null);
      setFiles([]);
      setStage("ingest");
      setProgress(0);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not remove the case.",
      );
    }
  }

  const loadedModelCount =
    backend
      ? Object.values(
          backend.models ??
            {},
        ).filter(
          (model) =>
            model.loaded,
        ).length
      : 0;

  const statusClass =
    !backend
      ? "offline"
      : backend.model_loaded
        ? "ready"
        : "warn";

  return (
    <div className="ra-app">
      <header className="ra-topbar">
        <div className="ra-brand">
          <div
            className="ra-brand-mark"
            aria-hidden="true"
          >
            <Microscope size={18} />
          </div>

          <div className="min-w-0">
            <div className="ra-brand-title">
              <span>
                RadAssist 3D
              </span>

              <span className="ra-brand-role">
                Research workstation
              </span>

              <span className="ra-build-tag">
                RESEARCH · QA
              </span>
            </div>

            <div className="ra-brand-subtitle">
              Multimodal AI · MPR · 3D · quantitative QA
            </div>
          </div>
        </div>

        <div
          className="ra-studybar"
          aria-live="polite"
        >
          <span className="ra-study-kicker">
            CURRENT STUDY
          </span>

          <div className="ra-study-title-row">
            <span
              className="ra-study-name"
              title={selectedSummary}
            >
              {selectedSummary}
            </span>

            {result?.is_demo && (
              <span className="ra-meta-chip demo">
                SYNTHETIC
              </span>
            )}
          </div>

          <div className="ra-study-meta">
            {result ? (
              <>
                <span className="ra-meta-chip">
                  {result.source_type}
                </span>

                <span className="ra-meta-chip">
                  {result.modality}
                </span>

                <span className="ra-meta-chip">
                  {result.original_dimensions.join(
                    " × ",
                  )}
                </span>

                <span className="ra-meta-chip">
                  {result.original_spacing_mm
                    .map((v) =>
                      v.toFixed(2),
                    )
                    .join(" × ")}{" "}
                  mm
                </span>

                <span
                  className={`ra-meta-chip ${
                    (
                      result
                        .measurement_quality
                        ?.status ??
                      "REVIEW"
                    ).toLowerCase()
                  }`}
                >
                  {result
                    .measurement_quality
                    ?.status ??
                    "REVIEW"}{" "}
                  QA
                </span>
              </>
            ) : (
              <span>
                Select a model and
                import a research
                imaging study
              </span>
            )}
          </div>
        </div>

        <div className="ra-statusbar">
          <div
            className={`ra-status-chip ${statusClass}`}
            title={
              backend?.model_error ??
              undefined
            }
          >
            <span
              className="ra-live-dot"
              aria-hidden="true"
            />

            <Server
              size={13}
              aria-hidden="true"
            />

            <span>
              {!backend
                ? "Backend offline"
                : `${loadedModelCount}/3 AI models ready · ${backend.device}`}
            </span>
          </div>

          <button
            type="button"
            className="ra-icon-btn"
            onClick={() =>
              window.location.reload()
            }
            aria-label="Refresh workspace"
            title="Refresh workspace"
          >
            <RefreshCw size={15} />
          </button>
        </div>
      </header>

      <nav
        className="ra-navbar"
        aria-label="Workspace navigation"
      >
        <div className="ra-navbar-group">
          <a
            href="#mpr"
            className="ra-nav-link active"
          >
            <ScanLine size={13} />
            MPR
          </a>

          <a
            href="#surface3d"
            className="ra-nav-link"
          >
            <Database size={13} />
            3D Surface
          </a>

          <a
            href="#metrics"
            className="ra-nav-link"
          >
            <Activity size={13} />
            Quantification
          </a>

          <a
            href="#qa"
            className="ra-nav-link"
          >
            <ShieldCheck size={13} />
            QA & Provenance
          </a>
        </div>

        <div className="ra-navbar-hint">
          Keyboard: ←→ slices ·
          W/L · pan · zoom · Esc
          exits fullscreen
        </div>
      </nav>

      <div className="ra-layout">
        <aside className="ra-sidebar">
          <section className="ra-sidebar-section">
            <div className="ra-import-card ra-enter ra-enter-1">
              <div className="ra-import-head">
                <div>
                  <div className="ra-import-title">
                    Study intake
                  </div>

                  <div className="ra-import-subtitle">
                    Local research
                    workflow · no
                    cloud upload
                    required
                  </div>
                </div>

                <div
                  className="ra-mini-icon"
                  aria-hidden="true"
                >
                  <UploadCloud size={15} />
                </div>
              </div>

              <div className="mt-4">
                <div className="mb-2 text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                  Segmentation model
                </div>

                <div className="grid gap-2">
                  {TARGET_ORDER.map(
                    (target) => {
                      const model =
                        backend?.models?.[
                          target
                        ] ??
                        FALLBACK_MODELS[
                          target
                        ];

                      const selected =
                        selectedTarget ===
                        target;

                      /*
                       * IMPORTANT:
                       * Model availability should NOT
                       * prevent selecting an anatomy.
                       *
                       * The Analyze button below is
                       * responsible for checking
                       * model.loaded.
                       */
                      const disabled =
                        working;

                      return (
                        <button
                          key={target}
                          type="button"
                          disabled={
                            disabled
                          }
                          onClick={() =>
                            handleTargetChange(
                              target,
                            )
                          }
                          className={`w-full rounded-xl border p-3 text-left transition ${
                            selected
                              ? "border-teal-300/30 bg-teal-300/[0.07]"
                              : "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04]"
                          } ${
                            disabled
                              ? "cursor-not-allowed opacity-45"
                              : ""
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span
                                  className={`inline-block size-2 rounded-full ${
                                    selected
                                      ? "bg-teal-300"
                                      : "bg-slate-600"
                                  }`}
                                />

                                <span className="text-[11px] font-semibold text-slate-200">
                                  {
                                    model.display_name
                                  }
                                </span>

                                <span className="rounded-full border border-white/[0.06] px-1.5 py-0.5 text-[8px] font-bold tracking-[0.08em] text-slate-500">
                                  {
                                    model.modality
                                  }
                                </span>
                              </div>

                              <div className="mt-1 text-[9px] leading-4 text-slate-600">
                                {
                                  model.description
                                }
                              </div>
                            </div>

                            <span
                              className={`rounded-full px-1.5 py-0.5 text-[8px] font-bold ${
                                model.loaded
                                  ? "border border-teal-300/10 bg-teal-300/[0.05] text-teal-200"
                                  : "border border-amber-300/10 bg-amber-300/[0.04] text-amber-200"
                              }`}
                            >
                              {model.loaded
                                ? "READY"
                                : "OFFLINE"}
                            </span>
                          </div>

                          <div className="mt-2 text-[8px] text-slate-700">
                            {
                              targetDescription(
                                target,
                              )
                            }
                          </div>
                        </button>
                      );
                    },
                  )}
                </div>

                <div className="mt-2 rounded-lg border border-white/[0.05] bg-black/10 px-2.5 py-2 text-[8px] text-slate-600">
                  <span className="text-slate-400">
                    Selected:
                  </span>{" "}
                  {targetLabel(
                    selectedTarget,
                  )}
                </div>
              </div>

              <div className="mt-4">
                <Dropzone
                  files={files}
                  onFilesChange={
                    setFiles
                  }
                  disabled={working}
                />
              </div>

              <div className="ra-actions mt-3">
                <button
                  type="button"
                  disabled={
                    working ||
                    !files.length ||
                    !selectedModel.loaded
                  }
                  onClick={() =>
                    void analyze()
                  }
                  className="ra-btn ra-btn-primary disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {working ? (
                    <LoaderCircle
                      size={14}
                      className="animate-spin"
                    />
                  ) : (
                    <ScanLine
                      size={14}
                    />
                  )}

                  Analyze{" "}
                  {
                    selectedModel.display_name
                  }
                </button>

                <button
                  type="button"
                  disabled={working}
                  onClick={() =>
                    void runDemo()
                  }
                  className="ra-btn disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <Sparkles size={14} />
                  Demo study
                </button>
              </div>

              {!selectedModel.loaded &&
                !working && (
                  <div className="mt-3 rounded-xl border border-amber-300/10 bg-amber-300/[0.035] p-3 text-[9px] leading-4 text-amber-100">
                    <strong>
                      {
                        selectedModel.display_name
                      }{" "}
                      model unavailable.
                    </strong>{" "}
                    You can still
                    select this anatomy.
                    Start the backend
                    and load the
                    corresponding model
                    before running
                    Analyze.
                  </div>
                )}

              {working && (
                <div
                  className="ra-progress"
                  aria-live="polite"
                >
                  <div className="ra-progress-row">
                    <span>
                      {stageMessage}
                    </span>

                    <span>
                      {progress}%
                    </span>
                  </div>

                  <div
                    className="ra-progress-track"
                    aria-hidden="true"
                  >
                    <div
                      className="ra-progress-fill"
                      style={{
                        width: `${Math.max(
                          4,
                          progress,
                        )}%`,
                      }}
                    />
                  </div>
                </div>
              )}
            </div>
          </section>

          <section className="ra-sidebar-section">
            <div className="ra-sidebar-title">
              Recent studies
            </div>

            <div className="ra-history-list">
              {history.length ===
                0 && (
                <div className="ra-sidebar-card p-4 text-center text-[10px] text-slate-600">
                  No completed
                  studies yet.
                </div>
              )}

              {history.map(
                (item) => (
                  <button
                    type="button"
                    key={item.case_id}
                    onClick={() =>
                      void openHistory(
                        item,
                      )
                    }
                    className="ra-history-item"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="ra-history-id">
                        {item.case_id.slice(
                          0,
                          14,
                        )}
                      </span>

                      {item.is_demo && (
                        <span className="rounded-full border border-amber-200/10 bg-amber-200/5 px-1.5 py-0.5 text-[8px] font-bold text-amber-100">
                          DEMO
                        </span>
                      )}
                    </div>

                    <div className="ra-history-meta">
                      <span>
                        {item.target.toUpperCase()}{" "}
                        ·{" "}
                        {item.modality}{" "}
                        ·{" "}
                        {
                          item.source_type
                        }
                      </span>

                      <span>
                        {item.volume_cm3 ==
                        null
                          ? "—"
                          : `${item.volume_cm3.toFixed(
                              1,
                            )} cm³`}
                      </span>
                    </div>

                    <div className="mt-1 text-[8px] text-slate-700">
                      {formatDate(
                        item.stored_at,
                      )}
                    </div>
                  </button>
                ),
              )}
            </div>
          </section>

          <section className="ra-sidebar-section">
            <div className="ra-sidebar-card p-3">
              <div className="flex items-center gap-2 text-[10px] font-semibold text-slate-200">
                <ShieldCheck
                  size={13}
                  className="text-teal-300"
                />

                Workflow guardrails
              </div>

              <div className="mt-2 space-y-1.5 text-[9px] leading-4 text-slate-600">
                <div>
                  • Source geometry
                  retained for final
                  metrics
                </div>

                <div>
                  • Model-specific
                  preprocessing is
                  kept separate
                </div>

                <div>
                  • Validation metrics
                  are model-level
                  references
                </div>

                <div>
                  • MRI intensity is
                  not treated as HU
                </div>
              </div>
            </div>
          </section>
        </aside>

        <main className="ra-main">
          <div className="ra-main-inner">
            <StageRail
              active={stage}
              result={result}
            />

            {error && (
              <div
                className="ra-error ra-enter"
                role="alert"
              >
                <AlertTriangle
                  size={16}
                  className="mt-0.5 shrink-0"
                />

                <div>
                  <div className="ra-error-title">
                    Pipeline message
                  </div>

                  <div className="ra-error-copy">
                    {error}
                  </div>
                </div>

                <button
                  type="button"
                  className="ml-auto inline-grid size-7 shrink-0 place-items-center rounded-lg text-slate-500 hover:bg-white/5 hover:text-white"
                  aria-label="Dismiss pipeline message"
                  onClick={() =>
                    setError(null)
                  }
                >
                  <X size={13} />
                </button>
              </div>
            )}

            {!result ? (
              <section className="ra-empty ra-enter ra-enter-2">
                <div className="ra-empty-content">
                  <div
                    className="ra-empty-mark"
                    aria-hidden="true"
                  >
                    <ScanLine
                      size={32}
                      strokeWidth={1.4}
                    />
                  </div>

                  <div className="ra-eyebrow">
                    AI-POWERED MEDICAL IMAGING WORKSTATION
                  </div>

                  <h1 className="ra-empty-title ra-heading">
                    From Medical Images
                    to Quantitative 3D Analysis.
                  </h1>

                  <p className="ra-empty-copy">
                    Import CT or MRI studies in DICOM or NIfTI, run anatomy-specific
                    AI segmentation, synchronize multiplanar views with 3D anatomy,
                    quantify structures, inspect segmentation QA, and export
                    reproducible research results with model and input provenance.
                  </p>

                  <div className="ra-empty-pills">
                    {[
                      "CT + MRI",
                      "DICOM + NIfTI",
                      "AI segmentation",
                      "MPR + 3D",
                      "Measurements",
                      "Segmentation QA",
                      "DICOM export",
                      "Provenance",
                    ].map(
                      (item) => (
                        <span
                          key={item}
                          className="ra-pill"
                        >
                          {item}
                        </span>
                      ),
                    )}
                  </div>
                </div>
              </section>
            ) : (
              <section className="ra-case-grid ra-enter ra-enter-2">
                <div className="ra-view-stack">
                  <div className="ra-study-strip">
                    <div className="ra-study-strip-left">
                      <div
                        className="ra-study-badge"
                        aria-hidden="true"
                      >
                        <Database
                          size={15}
                        />
                      </div>

                      <div className="min-w-0">
                        <div className="ra-study-strip-title">
                          {selectedSummary}
                        </div>

                        <div className="ra-study-strip-meta">
                          Case{" "}
                          {
                            result.request_id
                          }{" "}
                          · processed{" "}
                          {result.processing_seconds.toFixed(
                            2,
                          )}{" "}
                          s
                        </div>
                      </div>
                    </div>

                    <div className="ra-study-strip-actions">
                      {result.is_demo && (
                        <span className="rounded-full border border-amber-200/10 bg-amber-200/5 px-2.5 py-1 text-[8px] font-bold tracking-[0.08em] text-amber-100">
                          SYNTHETIC DEMO
                        </span>
                      )}

                      <button
                        type="button"
                        className="ra-icon-btn"
                        onClick={() =>
                          downloadJson(
                            result,
                          )
                        }
                        aria-label="Download JSON result"
                        title="Download JSON result"
                      >
                        <Download
                          size={14}
                        />
                      </button>

                      <button
                        type="button"
                        disabled={
                          result.persisted ===
                          false
                        }
                        className="ra-icon-btn disabled:cursor-not-allowed disabled:opacity-30"
                        onClick={() =>
                          void downloadArtifact(
                            caseMaskUrl(
                              result.request_id,
                            ),
                            "segmentation_mask.nii.gz",
                            setError,
                          )
                        }
                        aria-label="Download segmentation mask"
                        title="Download segmentation mask"
                      >
                        <FileDown
                          size={14}
                        />
                      </button>

                      <button
                        type="button"
                        disabled={
                          result.persisted ===
                          false
                        }
                        className="ra-icon-btn disabled:cursor-not-allowed disabled:opacity-30"
                        onClick={() =>
                          void downloadArtifact(
                            caseBundleUrl(
                              result.request_id,
                            ),
                            "radassist_case_bundle.zip",
                            setError,
                          )
                        }
                        aria-label="Download complete case bundle"
                        title="Download complete case bundle"
                      >
                        <Download
                          size={14}
                        />
                      </button>

                      <button
                        type="button"
                        disabled={result.persisted === false || result.dicom_export?.status !== "GENERATED"}
                        className="ra-icon-btn disabled:cursor-not-allowed disabled:opacity-30"
                        onClick={() =>
                          void downloadArtifact(
                            caseDicomSegUrl(result.request_id),
                            "radassist_segmentation.dcm",
                            setError,
                          )
                        }
                        aria-label="Download DICOM SEG"
                        title="Download DICOM SEG"
                      >
                        <FileDown size={14} />
                      </button>

                      <button
                        type="button"
                        disabled={result.persisted === false || result.dicom_export?.status !== "GENERATED"}
                        className="ra-icon-btn disabled:cursor-not-allowed disabled:opacity-30"
                        onClick={() =>
                          void downloadArtifact(
                            caseDicomSrUrl(result.request_id),
                            "radassist_measurements_sr.dcm",
                            setError,
                          )
                        }
                        aria-label="Download DICOM SR"
                        title="Download DICOM SR"
                      >
                        <FileDown size={14} />
                      </button>

                                            <button
                        type="button"
                        disabled={result.persisted === false}
                        className="ra-icon-btn disabled:cursor-not-allowed disabled:opacity-30"
                        onClick={() =>
                          void downloadArtifact(
                            caseReportUrl(result.request_id),
                            "radassist_structured_report.json",
                            setError,
                          )
                        }
                        aria-label="Download structured report"
                        title="Download structured report"
                      >
                        <FileDown size={14} />
                      </button>

                      <button
                        type="button"
                        className="ra-icon-btn danger"
                        onClick={() =>
                          void removeCurrent()
                        }
                        aria-label="Delete current case"
                        title="Delete current case"
                      >
                        <Trash2
                          size={14}
                        />
                      </button>
                    </div>
                  </div>

                  <div
                    id="mpr"
                    className="ra-workspace-card overflow-hidden p-0"
                  >
                    <ViewerErrorBoundary label="MPR">
                      {result.is_demo ? (
                        <DemoMPRViewer />
                      ) : (
                        <CornerstoneMPRViewer
                          volumeUrl={protectedVolumeUrl ?? ""}
                          caseId={
                            result.request_id
                          }
                        />
                      )}
                    </ViewerErrorBoundary>
                  </div>

                  <div
                    id="surface3d"
                    className="ra-workspace-card overflow-hidden p-0"
                  >
                    <ViewerErrorBoundary label="3D">
                      <Three3DMeshViewer
                        mesh={result.mesh}
                        labelMeshes={
                          result.label_meshes
                        }
                        target={
                          result.target
                        }
                      />
                    </ViewerErrorBoundary>
                  </div>
                </div>

                <aside
                  id="metrics"
                  className="ra-inspector"
                  aria-label="Quantification and QA"
                >
                  <div
                    id="qa"
                    className="scroll-mt-32"
                  />

                  <div className="ra-inspector-card ra-enter ra-enter-3 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="ra-section-label">
                          Quick readout
                        </div>

                        <div className="mt-1 text-[10px] text-slate-500">
                          Source-derived
                          measurements
                        </div>
                      </div>

                      <Activity
                        size={15}
                        className="text-teal-300"
                      />
                    </div>

                    <div className="mt-3 ra-metric-callout">
                      <div>
                        <div className="ra-section-label">
                          Target volume
                        </div>

                        <div className="mt-2">
                          <span className="ra-metric-value">
                            {result.volume_cm3.toFixed(
                              2,
                            )}
                          </span>

                          <span className="ra-metric-unit">
                            cm³
                          </span>
                        </div>

                        <div className="ra-metric-caption">
                          {result.voxel_count.toLocaleString()}{" "}
                          segmented
                          voxels
                        </div>
                      </div>

                      <div className="text-right">
                        <div className="ra-section-label">
                          Target
                        </div>

                        <div className="mt-1 text-[11px] font-semibold text-slate-200">
                          {result.target}
                        </div>
                      </div>
                    </div>

                    {result.label_metrics?.length >
                      0 && (
                      <div className="mt-3 space-y-2">
                        <div className="ra-section-label">
                          Structures
                        </div>

                        {result.label_metrics
                          .filter(
                            (metric) =>
                              metric.name.toLowerCase() !==
                              "background",
                          )
                          .map(
                            (
                              metric,
                            ) => (
                              <div
                                key={
                                  metric.label
                                }
                                className="rounded-lg border border-white/[0.05] bg-white/[0.02] p-2"
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <span className="text-[9px] font-medium text-slate-300">
                                    {
                                      metric.name
                                    }
                                  </span>

                                  <span className="font-mono text-[9px] text-teal-200">
                                    {
                                      metric.volume_cm3
                                    }{" "}
                                    cm³
                                  </span>
                                </div>

                                <div className="mt-1 text-[8px] text-slate-600">
                                  {metric.voxel_count.toLocaleString()}{" "}
                                  voxels ·{" "}
                                  {metric.fraction_pct.toFixed(
                                    2,
                                  )}
                                  %
                                </div>
                              </div>
                            ),
                          )}
                      </div>
                    )}

                    {result.validation_benchmark
                      .per_class &&
                      Object.keys(
                        result
                          .validation_benchmark
                          .per_class,
                      ).length >
                        0 && (
                        <div className="mt-3 ra-benchmark">
                          <div>
                            <strong>
                              Bundle validation
                            </strong>

                            <div className="mt-1">
                              Reference
                              metrics,
                              not
                              patient-specific
                              accuracy
                            </div>
                          </div>

                          <div className="space-y-1 text-right font-mono text-[8px]">
                            {Object.entries(
                              result
                                .validation_benchmark
                                .per_class,
                            ).map(
                              ([
                                name,
                                dice,
                              ]) => (
                                <div
                                  key={
                                    name
                                  }
                                >
                                  {name}:{" "}
                                  {dice.toFixed(
                                    2,
                                  )}
                                </div>
                              ),
                            )}
                          </div>
                        </div>
                      )}

                    {!result.validation_benchmark
                      .per_class ||
                    Object.keys(
                      result
                        .validation_benchmark
                        .per_class ??
                        {},
                    ).length ===
                      0 ? (
                      <div className="mt-2 ra-benchmark">
                        <div>
                          <strong>
                            Validation Dice
                          </strong>

                          <div className="mt-1">
                            Held-out
                            model
                            benchmark
                          </div>
                        </div>

                        <strong className="font-mono">
                          {result
                            .validation_benchmark
                            .validation_dice ==
                          null
                            ? "—"
                            : result.validation_benchmark.validation_dice.toFixed(
                                3,
                              )}
                        </strong>
                      </div>
                    ) : null}
                  </div>

                  <div className="ra-enter ra-enter-4">
                    <MetricsPanel
                      result={result}
                    />
                    <div className="mt-3">
                      <AdvancedAnalyticsPanel result={result} />
                    </div>
                  </div>
                </aside>
              </section>
            )}

            <footer className="ra-footer">
              <div className="flex items-center gap-2">
                <ShieldCheck size={12} />

                <span>
                  Research / engineering
                  use only · not a
                  diagnostic or treatment
                  device.
                </span>
              </div>

              <div className="flex items-center gap-4">
                <span>
                  <strong>
                    RadAssist 3D
                  </strong>{" "}
                  v1.4
                </span>

                <div
                  className="font-semibold"
                  style={{
                    color: "#FFD400",
                  }}
                >
                  This is created by Ruthwik Goparaju
                </div>

                <span className="font-mono">
                  API{" "}
                  {API_BASE_URL}
                </span>
              </div>
            </footer>
          </div>
        </main>
      </div>
    </div>
  );
}