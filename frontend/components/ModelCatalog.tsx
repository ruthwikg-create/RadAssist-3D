"use client";

import { Activity, Brain, CheckCircle2, CircleDot, HeartPulse, ScanLine, ShieldAlert } from "lucide-react";
import type { ModelInfo } from "../lib/types";

type Target = "spleen" | "heart" | "prostate" | "brain_tumor";

type CatalogItem = {
  target: Target;
  title: string;
  modality: string;
  input: string;
  description: string;
  labels: string[];
  kind: "ANATOMY" | "LESION";
};

const CATALOG: CatalogItem[] = [
  {
    target: "spleen",
    title: "Spleen",
    modality: "CT",
    input: "1 CT volume · DICOM series or NIfTI",
    description: "Whole-spleen anatomical segmentation with volumetry and 3D surface reconstruction.",
    labels: ["Spleen"],
    kind: "ANATOMY",
  },
  {
    target: "heart",
    title: "Heart · Ventricular",
    modality: "MR",
    input: "1 cardiac MR volume · short-axis research input",
    description: "LV blood pool, myocardium and RV blood pool segmentation. Review series compatibility before inference.",
    labels: ["LV pool", "Myocardium", "RV pool"],
    kind: "ANATOMY",
  },
  {
    target: "prostate",
    title: "Prostate · Zonal",
    modality: "MR",
    input: "1 prostate MRI volume · DICOM series or NIfTI",
    description: "Central gland and peripheral-zone segmentation with 3D anatomy and quantitative measurements.",
    labels: ["Central gland", "Peripheral zone"],
    kind: "ANATOMY",
  },
  {
    target: "brain_tumor",
    title: "Brain Tumor · BraTS",
    modality: "MR ×4",
    input: "T1c + T1 + T2 + FLAIR · aligned NIfTI volumes",
    description: "Whole tumor, tumor core and enhancing-tumor subregion segmentation for research review.",
    labels: ["Whole tumor", "Tumor core", "Enhancing tumor"],
    kind: "LESION",
  },
];

const icons = {
  spleen: ScanLine,
  heart: HeartPulse,
  prostate: Activity,
  brain_tumor: Brain,
};

export default function ModelCatalog({
  selectedTarget,
  models,
  working,
  onSelect,
}: {
  selectedTarget: Target;
  models: Record<string, ModelInfo>;
  working: boolean;
  onSelect: (target: Target) => void;
}) {
  const available = Object.values(models).filter((model) => model.loaded).length;
  const filters = [
    { key: "ALL", label: "ALL" },
    { key: "CT", label: "CT" },
    { key: "MR", label: "MRI" },
    { key: "LESION", label: "LESION / TUMOR" },
  ] as const;
  return (
    <div className="cw-model-catalog">
      <div className="cw-catalog-head">
        <div>
          <div className="cw-catalog-kicker">MODEL REGISTRY / ANALYSIS CONTRACT</div>
          <h2>SELECT THE DATA YOU ARE ADDING</h2>
          <p>Choose the anatomical or lesion model first. RadAssist then checks the uploaded study against that model's supported modality and input contract before inference.</p>
        </div>
        <div className="cw-catalog-status">
          <b>{available}/{CATALOG.length} READY</b>
          <span>research models loaded</span>
        </div>
      </div>
      <div className="cw-catalog-filters">
        {filters.map((filter) => (
          <button
            key={filter.key}
            type="button"
            className="cw-catalog-filter"
            onClick={(event) => {
              const root = event.currentTarget.closest(".cw-model-catalog");
              root?.querySelectorAll(".cw-model-card").forEach((card) => {
                const element = card as HTMLElement;
                element.hidden = filter.key !== "ALL" && element.dataset.filter !== filter.key && !(filter.key === "MR" && element.dataset.filter === "MR");
              });
            }}
          >
            {filter.label}
          </button>
        ))}
      </div>
      <div className="cw-model-grid">
        {CATALOG.map((item) => {
          const Icon = icons[item.target];
          const model = models[item.target];
          const loaded = Boolean(model?.loaded);
          return (
            <button
              key={item.target}
              type="button"
              data-filter={item.kind === "LESION" ? "LESION" : item.modality === "CT" ? "CT" : "MR"}
              className={`cw-model-card ${selectedTarget === item.target ? "active" : ""} `}
              onClick={() => onSelect(item.target)}
              disabled={working}
            >
              <div className="cw-model-card-top">
                <span className="cw-model-icon"><Icon size={18} /></span>
                <span className="cw-model-badges"><em>{item.modality}</em><em>{item.kind}</em></span>
                <span className={loaded ? "cw-model-ready" : "cw-model-offline"}>
                  {loaded ? <CheckCircle2 size={13} /> : <ShieldAlert size={13} />}
                  {loaded ? "READY" : "UNAVAILABLE"}
                </span>
              </div>
              <div className="cw-model-card-title">{item.title}</div>
              <div className="cw-model-card-description">{item.description}</div>
              <div className="cw-model-input"><CircleDot size={11} /><span>{item.input}</span></div>
              <div className="cw-model-labels">
                {item.labels.map((label) => <span key={label}>{label}</span>)}
              </div>
              <div className="cw-model-card-footer">
                <span>{model?.display_name ?? item.title}</span>
                <b>{selectedTarget === item.target ? "SELECTED" : "SELECT"}</b>
              </div>
            </button>
          );
        })}
      </div>
      <div className="cw-catalog-note">
        <ShieldAlert size={13} />
        <span><b>Unsupported data is not silently segmented.</b> CT, MR and other modalities require a model with a validated input contract. “Other” can be imported for inspection only until a compatible research model is installed.</span>
      </div>
    </div>
  );
}
