"use client";

import { Box, Orbit, Ratio, ScanLine, Sparkles } from "lucide-react";
import type { CaseResult } from "../lib/types";

function value(value: number | null | undefined, digits = 3, suffix = "") {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}${suffix}`;
}

export default function AdvancedAnalyticsPanel({ result }: { result: CaseResult }) {
  const metrics = result.advanced_metrics;
  const bbox = metrics?.bounding_box_mm;
  const spread = metrics?.principal_spread_mm;

  return (
    <div className="ra-advanced-card">
      <div className="ra-advanced-head">
        <div>
          <div className="ra-section-label">Advanced geometry analytics</div>
          <div className="ra-advanced-title">Shape intelligence beyond volume</div>
          <div className="ra-advanced-subtitle">
            Descriptive physical-space features for segmentation QA and research analysis.
          </div>
        </div>
        <Sparkles size={15} className="text-teal-300" />
      </div>

      <div className="ra-advanced-grid">
        <div className="ra-advanced-stat">
          <Box size={13} />
          <span>Bounding box</span>
          <strong>{bbox ? bbox.map((v) => value(v, 1)).join(" × ") + " mm" : "—"}</strong>
        </div>
        <div className="ra-advanced-stat">
          <Orbit size={13} />
          <span>Principal spread</span>
          <strong>{spread ? spread.map((v) => value(v, 1)).join(" × ") + " mm" : "—"}</strong>
        </div>
        <div className="ra-advanced-stat">
          <Ratio size={13} />
          <span>Sphericity</span>
          <strong>{value(metrics?.sphericity, 4)}</strong>
        </div>
        <div className="ra-advanced-stat">
          <ScanLine size={13} />
          <span>Surface / volume</span>
          <strong>{value(metrics?.surface_to_volume_cm_inv, 3, " cm⁻¹")}</strong>
        </div>
      </div>

      <div className="ra-advanced-foot">
        <span>Foreground voxels</span>
        <strong>{metrics?.foreground_voxels?.toLocaleString() ?? "—"}</strong>
        <span>·</span>
        <span>Compactness</span>
        <strong>{value(metrics?.compactness, 4)}</strong>
      </div>

      {result.input_notes?.length ? (
        <div className="ra-advanced-note">
          <strong>Input transformation</strong>
          {result.input_notes.map((note) => (
            <div key={note}>{note}</div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
