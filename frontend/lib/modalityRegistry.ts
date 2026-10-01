export type ImagingModality =
  | "CT" | "MR" | "XR" | "PET" | "SPECT" | "PET_CT" | "US" | "MG" | "FLUORO" | "DXA" | "NIFTI";

export type AnalysisCapability =
  | "viewer" | "mpr" | "segmentation" | "surface3d" | "quantification" | "fusion";

export type ModalityDefinition = {
  id: ImagingModality;
  label: string;
  description: string;
  acceptedFormats: string[];
  capabilities: AnalysisCapability[];
  status: "available" | "viewer-only" | "planned";
};

export const MODALITY_REGISTRY: ModalityDefinition[] = [
  { id: "CT", label: "CT", description: "Computed tomography", acceptedFormats: ["DICOM", "NIfTI"], capabilities: ["viewer", "mpr", "segmentation", "surface3d", "quantification"], status: "available" },
  { id: "MR", label: "MRI", description: "Magnetic resonance imaging", acceptedFormats: ["DICOM", "NIfTI"], capabilities: ["viewer", "mpr", "segmentation", "surface3d", "quantification"], status: "available" },
  { id: "XR", label: "X-Ray", description: "Projection radiography", acceptedFormats: ["DICOM", "PNG", "JPG"], capabilities: ["viewer"], status: "viewer-only" },
  { id: "PET", label: "PET", description: "Positron emission tomography", acceptedFormats: ["DICOM", "NIfTI"], capabilities: ["viewer", "mpr", "surface3d", "quantification"], status: "viewer-only" },
  { id: "SPECT", label: "SPECT", description: "Single-photon emission computed tomography", acceptedFormats: ["DICOM", "NIfTI"], capabilities: ["viewer", "mpr", "surface3d", "quantification"], status: "viewer-only" },
  { id: "PET_CT", label: "PET/CT", description: "Registered metabolic and anatomical imaging", acceptedFormats: ["DICOM"], capabilities: ["viewer", "mpr", "fusion", "surface3d", "quantification"], status: "viewer-only" },
  { id: "US", label: "Ultrasound", description: "Diagnostic ultrasound", acceptedFormats: ["DICOM", "PNG", "JPG"], capabilities: ["viewer"], status: "viewer-only" },
  { id: "MG", label: "Mammography", description: "Breast radiography", acceptedFormats: ["DICOM"], capabilities: ["viewer"], status: "viewer-only" },
  { id: "FLUORO", label: "Fluoroscopy", description: "Dynamic X-ray imaging", acceptedFormats: ["DICOM"], capabilities: ["viewer"], status: "viewer-only" },
  { id: "DXA", label: "DEXA", description: "Dual-energy X-ray absorptiometry", acceptedFormats: ["DICOM"], capabilities: ["viewer", "quantification"], status: "viewer-only" },
  { id: "NIFTI", label: "NIfTI Research Volume", description: "Research neuroimaging / volumetric input", acceptedFormats: [".nii", ".nii.gz"], capabilities: ["viewer", "mpr", "surface3d"], status: "available" },
];

export const SEGMENTATION_PROTOCOLS = {
  spleen: { label: "Spleen", modalities: ["CT"] as ImagingModality[] },
  heart: { label: "Heart", modalities: ["MR"] as ImagingModality[] },
  prostate: { label: "Prostate", modalities: ["MR"] as ImagingModality[] },
} as const;

export function modalityLabel(id: ImagingModality) {
  return MODALITY_REGISTRY.find((item) => item.id === id)?.label ?? id;
}
