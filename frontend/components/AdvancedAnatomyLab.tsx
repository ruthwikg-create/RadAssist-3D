"use client";

import {
  Activity, Brain, CircleDot, Crosshair, Dna, Eye, FileImage,
  FlaskConical, Layers3, Microscope, ShieldAlert, Stethoscope, Target, TriangleAlert
} from "lucide-react";
import type { CaseResult, BackendHealth } from "../lib/types";

type TargetKey = "spleen" | "heart" | "prostate" | "brain_tumor";

const MODELS: Array<{id:TargetKey;name:string;modality:string;input:string;architecture:string;labels:string[];purpose:string}> = [
  {id:"brain_tumor",name:"Brain Tumor MRI",modality:"MR",input:"T1c + T1 + T2 + FLAIR",architecture:"MONAI SegResNet 3D",labels:["tumor core","whole tumor","enhancing tumor"],purpose:"BraTS tumor subregion segmentation and 3D lesion review"},
  {id:"heart",name:"Cardiac Ventricular MRI",modality:"MR",input:"Cardiac short-axis MRI",architecture:"2D MONAI UNet + SliceInferer",labels:["LV blood pool","myocardium","RV blood pool"],purpose:"Ventricular structure segmentation and 3D reconstruction"},
  {id:"prostate",name:"Prostate MRI Anatomy",modality:"MR",input:"Prostate MRI volume",architecture:"MONAI 3D segmentation",labels:["central gland","peripheral zone"],purpose:"Zonal anatomy segmentation and quantitative morphology"},
  {id:"spleen",name:"Spleen CT",modality:"CT",input:"Abdominal CT volume",architecture:"MONAI SegResNet",labels:["spleen"],purpose:"Organ segmentation, mesh reconstruction and quantitative QA"},
];

const PLANNED_LESIONS = [
  ["Brain MRI","Glioma / intracranial lesion","3D lesion mask + volume + longest diameter","MONAI BraTS MRI segmentation"],
  ["Chest CT","Pulmonary nodule / mass","Candidate localization + morphology + review","MONAI lung_nodule_ct_detection"],
  ["Liver CT/MRI","Focal liver lesion","Lesion mask + volume + enhancement workflow"],
  ["Prostate MRI","Suspicious lesion","Lesion candidate map + zonal context"],
] as const;

function SectionCard({title,eyebrow,children}:{title:string;eyebrow?:string;children:React.ReactNode}) {
  return <section className="aal-card"><div className="aal-card-head"><div>{eyebrow ? <span className="aal-eyebrow">{eyebrow}</span> : null}<h2>{title}</h2></div></div>{children}</section>;
}

export default function AdvancedAnatomyLab({result,backend}:{result:CaseResult|null;backend:BackendHealth|null}) {
  const target = (result?.target ?? "heart") as TargetKey;
  const active = MODELS.find((item) => item.id === target) ?? MODELS[0];
  const loaded = backend?.models?.[target]?.loaded ?? false;
  const labels = result?.label_metrics?.filter((item) => item.name.toLowerCase() !== "background") ?? [];
  const compatibility = result?.model_compatibility;

  return (
    <div className="aal">
      <div className="aal-hero">
        <div>
          <div className="aal-kicker">ANATOMY LAB / MODEL LIBRARY / 3D EXPLANATION</div>
          <h1>Imaging Anatomy &amp; AI Model Explorer</h1>
          <p>A transparent workspace that shows which image type is loaded, which research model is being used, what structures it can segment, and how the 3D surface is derived from the source volume.</p>
        </div>
        <div className="aal-status"><span className={"aal-led " + (loaded ? "good" : "warn")} /><b>{loaded ? "MODEL LOADED" : "MODEL STATUS REVIEW"}</b><small>{result ? result.source_type + " · " + result.modality : "No active study"}</small></div>
      </div>

      <div className="aal-grid">
        <SectionCard title="Image & Model Library" eyebrow="01 / INPUT → MODEL">
          <div className="aal-model-grid">
            {MODELS.map((model) => {
              const modelLoaded = backend?.models?.[model.id]?.loaded ?? false;
              const selected = model.id === target;
              return <article key={model.id} className={"aal-model " + (selected ? "selected" : "")}>
                <div className="aal-model-icon">{model.id === "heart" ? <Activity size={20}/> : model.id === "prostate" ? <Dna size={20}/> : model.id === "brain_tumor" ? <Brain size={20}/> : <CircleDot size={20}/>}</div>
                <div className="aal-model-top"><b>{model.name}</b><span className={modelLoaded ? "good" : "warn"}>{modelLoaded ? "READY" : "CHECK"}</span></div>
                <div className="aal-model-meta"><span><FileImage size={12}/> {model.modality}</span><span><Layers3 size={12}/> {model.architecture}</span></div>
                <p>{model.purpose}</p>
                <div className="aal-chip-row">{model.labels.map((label) => <span key={label}>{label}</span>)}</div>
                <div className="aal-model-foot"><span>Expected input</span><b>{model.input}</b></div>
              </article>;
            })}
            <article className="aal-model aal-planned">
              <div className="aal-model-icon"><Activity size={20}/></div>
              <div className="aal-model-top"><b>Whole-Heart Multi-Structure</b><span className="warn">MODEL REQUIRED</span></div>
              <div className="aal-model-meta"><span><FileImage size={12}/> MR / cardiac cine</span><span><Layers3 size={12}/> 3D multi-label model</span></div>
              <p>Target architecture for the complete 3D anatomy shown in the reference workflow, including chambers, myocardium and major vessels.</p>
              <div className="aal-chip-row">{["LA","RA","LV","RV","myocardium","aorta","pulmonary artery","SVC / IVC"].map((label) => <span key={label}>{label}</span>)}</div>
              <div className="aal-model-foot"><span>Status</span><b>Requires dedicated whole-heart checkpoint</b></div>
            </article>
          </div>
        </SectionCard>

        <SectionCard title="Current Study Contract" eyebrow="02 / SOURCE VERIFICATION">
          <div className="aal-contract">
            <div><span>Target</span><b>{result?.target?.toUpperCase() ?? "—"}</b></div>
            <div><span>Source</span><b>{result?.source_type ?? "—"}</b></div>
            <div><span>Modality</span><b>{result?.modality ?? "—"}</b></div>
            <div><span>Volume</span><b>{result?.original_dimensions?.join(" × ") ?? "—"}</b></div>
            <div><span>Spacing</span><b>{result?.original_spacing_mm?.map((v) => v.toFixed(2)).join(" × ") ?? "—"} mm</b></div>
            <div><span>AI model</span><b>{result?.model_provenance?.name ?? "—"}</b></div>
            <div><span>Architecture</span><b>{result?.model_provenance?.architecture ?? "—"}</b></div>
            <div><span>QA gate</span><b className={result?.measurement_quality?.status === "PASS" ? "good" : "warn"}>{result?.measurement_quality?.status ?? "REVIEW"}</b></div>
            <div><span>Model domain</span><b className="warn">{compatibility?.status ?? "NOT_CHECKED"}</b></div>
          </div>
          <div className="aal-callout"><ShieldAlert size={16}/><div><b>Compatibility is part of the result</b><p>RadAssist does not silently convert an incompatible model into a plausible-looking anatomy. Cardiac ventricular models require appropriate cardiac MR input; a fragmented mask is surfaced as a QA issue instead of being cosmetically repaired.</p>{compatibility?.warnings?.length ? <ul className="aal-warning-list">{compatibility.warnings.slice(0,3).map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}</div></div>
        </SectionCard>

        <SectionCard title="How the 3D Anatomy Is Built" eyebrow="03 / SOURCE → 3D">
          <div className="aal-pipeline">
            {[
              ["01","Source volume","DICOM / NIfTI",<FileImage size={18}/>],
              ["02","AI labelmap","Voxel-level classes",<Layers3 size={18}/>],
              ["03","Physical geometry","Spacing + direction + origin",<Crosshair size={18}/>],
              ["04","Surface mesh","Marching cubes + QA",<TriangleAlert size={18}/>],
              ["05","Review","MPR + 3D + measurements",<Eye size={18}/>],
            ].map(([number,title,detail,icon]) => <div key={String(number)} className="aal-pipe-step"><div className="aal-pipe-num">{number}</div><div className="aal-pipe-icon">{icon}</div><b>{title}</b><span>{detail}</span></div>)}
          </div>
          <div className="aal-3d-explainer">
            <div className="aal-3d-frame"><div className="aal-wire-surface surface-a"/><div className="aal-wire-surface surface-b"/><div className="aal-axis axis-x"/><div className="aal-axis axis-y"/><div className="aal-axis axis-z"/><span className="axis-label x">X</span><span className="axis-label y">Y</span><span className="axis-label z">Z</span></div>
            <div className="aal-3d-notes">
              <div><b>Physical coordinates</b><span>Mesh vertices are generated in source physical space rather than arbitrary screen coordinates.</span></div>
              <div><b>Per-structure surfaces</b><span>Each anatomical label can be isolated, hidden, made transparent, clipped and inspected independently.</span></div>
              <div><b>Quantitative cross-check</b><span>Labelmap volume and mesh geometry are compared before a research result is marked for review.</span></div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="3D Anatomy Explanation" eyebrow="04 / ACTIVE CASE">
          <div className="aal-anatomy-head"><div><b>{active.name}</b><span>{active.modality} · {active.architecture}</span></div><span className={"aal-badge " + (loaded ? "good" : "warn")}>{loaded ? "AI ENABLED" : "MODEL CHECK"}</span></div>
          <div className="aal-structure-grid">
            {labels.length ? labels.map((item,index) => <div className="aal-structure" key={item.label}><i className={"aal-structure-dot s" + (index % 4)}/><div><b>{item.name}</b><span>{item.volume_cm3.toFixed(2)} cm³ · {item.voxel_count.toLocaleString()} voxels</span></div></div>) : active.labels.map((label,index) => <div className="aal-structure" key={label}><i className={"aal-structure-dot s" + (index % 4)}/><div><b>{label}</b><span>Available label class · load a compatible study to quantify</span></div></div>)}
          </div>
          <div className="aal-review-grid">
            <div><span>Connected components</span><b>{result?.measurement_quality?.connected_components ?? "—"}</b></div>
            <div><span>Largest component</span><b>{result?.measurement_quality?.largest_component_fraction_pct != null ? result.measurement_quality.largest_component_fraction_pct.toFixed(1) + "%" : "—"}</b></div>
            <div><span>Mesh / labelmap ΔV</span><b>{result?.measurement_quality?.volume_difference_pct != null ? result.measurement_quality.volume_difference_pct.toFixed(2) + "%" : "—"}</b></div>
            <div><span>Surface area</span><b>{result?.measurement_quality?.surface_area_cm2 != null ? result.measurement_quality.surface_area_cm2.toFixed(2) + " cm²" : "—"}</b></div>
          </div>
        </SectionCard>

        <SectionCard title="Tumor & Lesion Screening" eyebrow="05 / OPTIONAL PATHOLOGY MODULE">
          <div className="aal-tumor-banner"><Target size={20}/><div><b>Research lesion detection layer</b><p>Tumor detection is kept separate from anatomy segmentation. It requires a pathology-specific, modality-specific checkpoint and validation dataset; the current repository does not contain such a validated checkpoint.</p></div><span className="aal-badge warn">CHECKPOINT REQUIRED</span></div>
          <div className="aal-lesion-grid">{PLANNED_LESIONS.map(([image,lesion,output,reference]) => <article key={image}><div><Microscope size={14}/><b>{image}</b></div><strong>{lesion}</strong><span>{output}</span><em>Not configured</em><small>{reference ?? "Pathology-specific checkpoint"}</small></article>)}</div>
          <div className="aal-tumor-output"><b>When a validated lesion model is configured, this panel is designed to expose:</b><div className="aal-chip-row">{["candidate mask","3D lesion surface","volume","longest diameter","location","confidence / uncertainty","review status","source + model provenance"].map((item) => <span key={item}>{item}</span>)}</div></div>
          <div className="aal-callout amber"><TriangleAlert size={16}/><div><b>No tumor finding is generated by placeholder logic</b><p>This prevents intensity artifacts or segmentation fragments from being presented as a tumor.</p></div></div>
        </SectionCard>

        <SectionCard title="Education Mode" eyebrow="06 / MBBS + BIOMEDICAL LEARNING">
          <div className="aal-education-grid">
            <article><Stethoscope size={17}/><b>Anatomy-first view</b><span>Toggle individual structures and correlate each 3D surface with MPR slices.</span></article>
            <article><Brain size={17}/><b>Plane-aware study</b><span>Compare axial, coronal and sagittal views while inspecting the selected structure.</span></article>
            <article><FlaskConical size={17}/><b>Quantitative learning</b><span>Teach volume, surface area, equivalent diameter and mesh/labelmap agreement from the same case.</span></article>
            <article><ShieldAlert size={17}/><b>Critical appraisal</b><span>Students can see why a segmentation is marked PASS, REVIEW or FAIL instead of treating every AI output as ground truth.</span></article>
          </div>
        </SectionCard>

        <SectionCard title="Clinician / Research Review Workflow" eyebrow="07 / HUMAN-IN-THE-LOOP">
          <div className="aal-review-flow">{[
            ["1","Verify source","Confirm modality, anatomy, sequence/series and geometry."],
            ["2","Inspect MPR","Review axial, sagittal and coronal source images."],
            ["3","Inspect AI","Toggle structures and inspect raw/cleaned QA metadata."],
            ["4","Inspect 3D","Rotate, clip, isolate and compare anatomical surfaces."],
            ["5","Review QA","Check topology, boundary contact and mesh/labelmap agreement."],
            ["6","Export","Create research artifacts with provenance and model hash."],
          ].map(([n,title,detail]) => <div key={n}><b>{n}</b><strong>{title}</strong><span>{detail}</span></div>)}</div>
        </SectionCard>
      </div>
    </div>
  );
}
