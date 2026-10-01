export type HUStatistics = {
  mean_hu: number | null;
  std_hu: number | null;
  min_hu: number | null;
  max_hu: number | null;
  median_hu: number | null;
  p05_hu: number | null;
  p95_hu: number | null;
};

export type ValidationBenchmark = {
  validation_dice: number | null;
  target_threshold: number;
  per_class?: Record<string, number>;
};

export type LabelMetric = {
  label: number;
  name: string;
  voxel_count: number;
  volume_cm3: number;
  fraction_pct: number;
};

export type LabelMeshData = MeshData & {
  label: number;
  name: string;
  mesh_step_size: number;
};

export type LabelComponentQA = {
  label: number;
  name: string;
  connected_components: number;
  largest_component_fraction_pct: number | null;
};

export type MeasurementQuality = {
  status: "PASS" | "REVIEW" | "FAIL" | string;
  measurement_method: string;
  voxel_volume_mm3: number;
  labelmap_volume_cm3: number;
  equivalent_diameter_mm: number | null;
  mask_fraction_pct: number;
  connected_components: number;
  largest_component_fraction_pct: number | null;
  touches_volume_boundary: boolean;
  surface_area_cm2: number | null;
  mesh_volume_cm3: number | null;
  volume_difference_pct: number | null;
  centroid_mm: number[] | null;
  intensity_domain: string;
  hu_calibrated: boolean;
  mean_intensity?: number | null;
  std_intensity?: number | null;
  min_intensity?: number | null;
  max_intensity?: number | null;
  median_intensity?: number | null;
  p05_intensity?: number | null;
  p95_intensity?: number | null;
  rescale_slope: number | null;
  rescale_intercept: number | null;
  flags: string[];
};

export type ModelProvenance = {
  name: string;
  architecture: string;
  dataset: string;
  checkpoint_loaded: boolean;
  checkpoint_sha256: string | null;
  preprocessing: Record<string, unknown>;
  labels?: Record<string, string>;
};

export type MeshData = {
  vertices: number[][];
  faces: number[][];
  vertex_count: number;
  face_count: number;
};

export type ModelInfo = {
  display_name: string;
  modality: string;
  description: string;
  labels: Record<string, string>;
  loaded: boolean;
  error: string | null;
};

export type ModelsResponse = {
  models: Record<string, ModelInfo>;
};

export type BackendHealth = {
  status: string;
  service: string;
  version: string;
  device: string;
  model_loaded: boolean;
  model_error: string | null;
  models: Record<string, ModelInfo>;
};

export type CaseResult = {
  request_id: string;
  target: string;
  source_type: string;
  modality: string;
  is_demo: boolean;

  volume_cm3: number;
  voxel_count: number;

  hu_statistics: HUStatistics;

  validation_benchmark: ValidationBenchmark;

  label_metrics: LabelMetric[];

  label_meshes?: Record<string, LabelMeshData>;

  label_component_qa?: Record<string, LabelComponentQA>;

  heart_slice_qa?: {
    status: string;
    slice_count: number;
    foreground_slices: number;
    foreground_slice_fraction_pct?: number;
    label_slice_coverage_pct?: Record<string, number>;
    note?: string;
  };

  measurement_quality?: MeasurementQuality;

  model_provenance?: ModelProvenance;

  mesh: MeshData;

  original_spacing_mm: number[];
  original_dimensions: number[];

  processing_seconds: number;
  stage_timings_seconds?: Record<string, number>;
  mesh_step_size: number;

  preview: {
    volume_url: string;
    mask_url: string;
  };

  warnings: string[];

  stored_at?: string;

  provenance_record?: Record<string, unknown>;
  structured_measurements?: Record<string, unknown>;
  dicom_seg_result?: Record<string, unknown>;
  dicom_sr_result?: Record<string, unknown>;
  uncertainty_status?: Record<string, unknown>;
  input_validation?: Record<string, unknown>;

  persisted?: boolean;
};

export type CaseSummary = {
  case_id: string;
  target: string;
  source_type: string;
  modality: string;
  volume_cm3: number | null;
  stored_at: string | null;
  is_demo: boolean;
};