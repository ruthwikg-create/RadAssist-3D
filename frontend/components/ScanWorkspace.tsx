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
      onSettings={() => setShowSettings((value) => !value)}
      importContent={
        <div className="cw-import-stack">
          <div className="cw-import-targets">
            {TARGET_ORDER.map((target) => (
              <button
                key={target}
                type="button"
                className={`cw-target ${selectedTarget === target ? "active" : ""}`}
                onClick={() => handleTargetChange(target)}
                disabled={working}
              >
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
                <CornerstoneMPRViewer
                  volumeUrl={protectedVolumeUrl ?? ""}
                  caseId={result.request_id}
                />
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