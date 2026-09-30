"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Check,
  Circle,
  Database,
  GitCompare,
  Download,
  FileDown,
  LoaderCircle,
  Microscope,
  RefreshCw,
  ScanLine,
  Server,
  ShieldCheck,
  SlidersHorizontal,
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
import CaseComparisonPanel from "./CaseComparisonPanel";
import ResearchAnalyticsPanel from "./ResearchAnalyticsPanel";
import ClinicalResearchConsole from "./ClinicalResearchConsole";
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

  const [comparison, setComparison] =
    useState<CaseResult | null>(null);

  const [activeSection, setActiveSection] =
    useState<"mpr" | "surface3d" | "metrics" | "qa" | "research">("mpr");
  const [showSettings, setShowSettings] = useState(false);
  const [compactWorkspace, setCompactWorkspace] = useState(false);
  const [showInspector, setShowInspector] = useState(true);
  const [workstationMode, setWorkstationMode] = useState<"mpr" | "ai" | "research">("research");

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
    const ids = ["mpr", "surface3d", "metrics", "qa", "research"];
    const elements = ids.map((id) => document.getElementById(id)).filter(Boolean) as HTMLElement[];
    if (!elements.length) return;
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (visible?.target?.id) setActiveSection(visible.target.id as typeof activeSection);
    }, { rootMargin: "-18% 0px -62% 0px", threshold: [0.15, 0.35, 0.6] });
    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [result]);

  function jumpToSection(id: typeof activeSection) {
    setActiveSection(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  useEffect(() => {
    let disposed = false;

    const refreshStatus = async () => {
      try {
        const health = await fetchHealth();
        if (!disposed) setBackend(health);
      } catch {
        if (!disposed) setBackend(null);
      }
    };

    void (async () => {
      await refreshStatus();

      try {
        const cases = await listCases();
        if (!disposed) setHistory(cases);
      } catch {
        if (!disposed) setHistory([]);
      }
    })();

    const timer = window.setInterval(
      () => void refreshStatus(),
      5000,
    );

    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
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
    setComparison(null);
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

  async function compareWithLatestCompatible() {
    if (!result || working) return;

    const candidate = history.find(
      (item) =>
        item.case_id !== result.request_id &&
        item.target === result.target &&
        item.modality === result.modality,
    );

    if (!candidate) {
      setError("No previous compatible study is available for comparison.");
      return;
    }

    setWorking(true);
    setError(null);
    try {
      setComparison(await getCase(candidate.case_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load comparison study.");
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

  async function refreshCurrentCase() {
    if (!result || working) return;
    setWorking(true);
    setError(null);
    try {
      const refreshed = await getCase(result.request_id);
      setResult(refreshed);
      setStage("render");
      setProgress(100);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to refresh the stored QA result.");
    } finally {
      setWorking(false);
    }
  }

  function openImportPicker() {
    const input = document.querySelector<HTMLInputElement>("#radassist-import-input");
    if (input) {
      input.click();
      return;
    }
    document.getElementById("cw-import-zone")?.scrollIntoView({ behavior: "smooth", block: "center" });
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
    <ClinicalResearchConsole
      result={result}
      backend={backend}
      history={history}
      mode={workstationMode}
      onModeChange={setWorkstationMode}
      onOpenHistory={(item) => void openHistory(item)}
      onImport={openImportPicker}
      onRefreshCase={() => void refreshCurrentCase()}
      onDownload={(path, filename) => void downloadArtifact(path, filename, setError)}
      onSetError={setError}
      onCompare={() => void compareWithLatestCompatible()}
      onSettings={() => setShowSettings((value: boolean) => !value)}
      importContent={
        <div className="cw-import-stack">
          <div className="cw-import-targets">
            {TARGET_ORDER.map((target) => (
              <button key={target} type="button" className={`cw-target ${selectedTarget === target ? "active" : ""}`} onClick={() => handleTargetChange(target)} disabled={working}>
                {targetLabel(target)}
              </button>
            ))}
          </div>
          <Dropzone
            files={files}
            onFilesChange={setFiles}
            disabled={working}
            modalityLabel={selectedModel.modality === "MR" ? "MR" : "CT"}
          />
          <div className="cw-import-actions">
            <button type="button" className="cw-primary" disabled={working || !files.length || !selectedModel.loaded} onClick={() => void analyze()}>
              {working ? "Processing…" : `Analyze ${selectedModel.display_name}`}
            </button>
            <button type="button" className="cw-secondary" disabled={working || !backend?.demo_enabled} onClick={() => void runDemo()}>
              Run demo
            </button>
          </div>
        </div>
      }
      viewerContent={
        result ? (
          <div className="cw-viewer-stack">
            <ViewerErrorBoundary label="MPR">
              {result.is_demo ? (
                <DemoMPRViewer />
              ) : (
                <CornerstoneMPRViewer volumeUrl={protectedVolumeUrl ?? ""} caseId={result.request_id} />
              )}
            </ViewerErrorBoundary>
            <ViewerErrorBoundary label="3D">
              <Three3DMeshViewer
                mesh={result.mesh}
                labelMeshes={result.label_meshes}
                meshDiagnostics={result.mesh_diagnostics}
                target={result.target}
              />
            </ViewerErrorBoundary>
            <div className="cw-viewer-metrics">
              <MetricsPanel result={result} />
              <AdvancedAnalyticsPanel result={result} />
              {comparison ? <CaseComparisonPanel current={result} previous={comparison} /> : null}
            </div>
          </div>
        ) : null
      }
    />
  );
}