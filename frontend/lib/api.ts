import type {
  BackendHealth,
  CaseResult,
  CaseSummary,
  ModelsResponse,
} from "./types";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

function absoluteUrl(path: string) {
  if (/^https?:\/\//.test(path)) return path;

  return `${API_BASE_URL}${
    path.startsWith("/") ? path : `/${path}`
  }`;
}

export async function fetchHealth(): Promise<BackendHealth> {
  const response = await fetch(
    `${API_BASE_URL}/health`,
    {
      cache: "no-store",
    },
  );

  if (!response.ok) {
    throw new Error(
      "Backend health check failed.",
    );
  }

  return response.json() as Promise<BackendHealth>;
}

export async function fetchModels(): Promise<ModelsResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/models`,
    {
      cache: "no-store",
    },
  );

  if (!response.ok) {
    throw new Error(
      "Could not load model registry.",
    );
  }

  return response.json() as Promise<ModelsResponse>;
}

export function segmentFiles(
  target: string,
  files: File[],
  onProgress?: (progress: number) => void,
): Promise<CaseResult> {
  return new Promise(
    (resolve, reject) => {
      const form = new FormData();

      form.append(
        "target",
        target,
      );

      files.forEach(
        (file) => {
          form.append(
            "files",
            file,
            file.name,
          );
        },
      );

      const xhr =
        new XMLHttpRequest();

      xhr.open(
        "POST",
        `${API_BASE_URL}/api/v1/segment`,
      );

      xhr.responseType = "json";

      xhr.timeout =
        60 * 60 * 1000;

      xhr.upload.onprogress = (
        event,
      ) => {
        if (
          event.lengthComputable &&
          onProgress
        ) {
          onProgress(
            Math.round(
              (event.loaded /
                event.total) *
                100,
            ),
          );
        }
      };

      xhr.onerror = () =>
        reject(
          new Error(
            "Unable to reach the RadAssist backend.",
          ),
        );

      xhr.ontimeout = () =>
        reject(
          new Error(
            "The analysis request timed out.",
          ),
        );

      xhr.onabort = () =>
        reject(
          new Error(
            "The analysis request was cancelled.",
          ),
        );

      xhr.onload = () => {
        let body: unknown =
          xhr.response;

        if (!body) {
          try {
            body = JSON.parse(
              xhr.responseText,
            );
          } catch {
            body = null;
          }
        }

        if (
          xhr.status >= 200 &&
          xhr.status < 300
        ) {
          resolve({
            ...(body as CaseResult),
            persisted: true,
          });

          return;
        }

        const detail =
          typeof body ===
            "object" &&
          body !== null &&
          "detail" in body
            ? String(
                (
                  body as {
                    detail?: unknown;
                  }
                ).detail ?? "",
              )
            : `Backend returned HTTP ${xhr.status}.`;

        reject(
          new Error(detail),
        );
      };

      xhr.send(form);
    },
  );
}

function buildLocalDemoMesh() {
  const vertices: number[][] = [];
  const faces: number[][] = [];

  const rings = 18;
  const segments = 28;

  const rx = 34;
  const ry = 24;
  const rz = 29;

  for (
    let ring = 0;
    ring <= rings;
    ring += 1
  ) {
    const v =
      ring / rings;

    const phi =
      v * Math.PI;

    const sinPhi =
      Math.sin(phi);

    const cosPhi =
      Math.cos(phi);

    for (
      let segment = 0;
      segment < segments;
      segment += 1
    ) {
      const u =
        segment / segments;

      const theta =
        u * Math.PI * 2;

      vertices.push([
        rx *
          sinPhi *
          Math.cos(theta),
        ry * cosPhi,
        rz *
          sinPhi *
          Math.sin(theta),
      ]);
    }
  }

  for (
    let ring = 0;
    ring < rings;
    ring += 1
  ) {
    for (
      let segment = 0;
      segment < segments;
      segment += 1
    ) {
      const next =
        (segment + 1) %
        segments;

      const a =
        ring * segments +
        segment;

      const b =
        ring * segments +
        next;

      const c =
        (ring + 1) *
          segments +
        next;

      const d =
        (ring + 1) *
          segments +
        segment;

      faces.push(
        [a, d, b],
        [b, d, c],
      );
    }
  }

  return {
    vertices,
    faces,
    vertex_count:
      vertices.length,
    face_count:
      faces.length,
  };
}

function buildLocalDemoCase(): CaseResult {
  const now =
    new Date().toISOString();

  const requestId =
    `local-demo-${Date.now().toString(36)}`;

  const a = 34;
  const b = 24;
  const c = 29;

  const volumeCm3 =
    (4 / 3) *
    Math.PI *
    a *
    b *
    c /
    1000;

  const mesh =
    buildLocalDemoMesh();

  return {
    request_id: requestId,

    target: "spleen",

    source_type: "SYNTHETIC",

    modality: "CT",

    is_demo: true,

    volume_cm3:
      Number(
        volumeCm3.toFixed(2),
      ),

    voxel_count: 26000,

    hu_statistics: {
      mean_hu: 72,
      std_hu: 6.8,
      min_hu: 51,
      max_hu: 93,
      median_hu: 72,
      p05_hu: 61,
      p95_hu: 83,
    },

    validation_benchmark: {
      validation_dice: null,
      target_threshold: 0.9,
      per_class: {},
    },

    label_metrics: [
      {
        label: 1,
        name: "spleen",
        voxel_count: 26000,
        volume_cm3:
          Number(
            volumeCm3.toFixed(2),
          ),
        fraction_pct: 100,
      },
    ],

    mesh,

    original_spacing_mm: [
      1.5,
      1.5,
      2.0,
    ],

    original_dimensions: [
      96,
      96,
      64,
    ],

    processing_seconds: 0.04,

    mesh_step_size: 1,

    preview: {
      volume_url: "",
      mask_url: "",
    },

    warnings: [
      "Synthetic browser demo. No patient data and no clinical inference are being represented.",
      "This local fallback is intentionally not persisted to the backend.",
    ],

    stored_at: now,

    persisted: false,
  };
}

export async function createDemoCase(): Promise<CaseResult> {
  return buildLocalDemoCase();
}

export async function getCase(
  caseId: string,
): Promise<CaseResult> {
  const response =
    await fetch(
      `${API_BASE_URL}/api/v1/cases/${encodeURIComponent(caseId)}`,
      {
        cache: "no-store",
      },
    );

  const body =
    await response
      .json()
      .catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      body?.detail ??
        "Case retrieval failed.",
    );
  }

  return {
    ...(body as CaseResult),
    persisted: true,
  };
}

export async function listCases(): Promise<
  CaseSummary[]
> {
  const response =
    await fetch(
      `${API_BASE_URL}/api/v1/cases`,
      {
        cache: "no-store",
      },
    );

  if (!response.ok) {
    throw new Error(
      "Could not load case history.",
    );
  }

  return response.json() as Promise<
    CaseSummary[]
  >;
}

export async function deleteCase(
  caseId: string,
): Promise<void> {
  const response =
    await fetch(
      `${API_BASE_URL}/api/v1/cases/${encodeURIComponent(caseId)}`,
      {
        method: "DELETE",
      },
    );

  if (!response.ok) {
    const body =
      await response
        .json()
        .catch(() => ({}));

    throw new Error(
      body?.detail ??
        "Could not delete the case.",
    );
  }
}

export function toPreviewUrl(
  path: string,
) {
  return absoluteUrl(path);
}

export function caseMaskUrl(
  caseId: string,
) {
  return `${API_BASE_URL}/api/v1/cases/${encodeURIComponent(caseId)}/mask`;
}

export function caseBundleUrl(
  caseId: string,
) {
  return `${API_BASE_URL}/api/v1/cases/${encodeURIComponent(caseId)}/bundle`;
}

export function caseReportUrl(caseId: string) {
  return `${API_BASE_URL}/api/v1/cases/${encodeURIComponent(caseId)}/report`;
}
export function caseDicomSegUrl(caseId: string) {
  return `${API_BASE_URL}/api/v1/cases/${encodeURIComponent(caseId)}/dicom-seg`;
}

export function caseDicomSrUrl(caseId: string) {
  return `${API_BASE_URL}/api/v1/cases/${encodeURIComponent(caseId)}/dicom-sr`;
}


export async function downloadApiFile(
  path: string,
  filename: string,
) {
  const response =
    await fetch(
      absoluteUrl(path),
      {
        cache: "no-store",
      },
    );

  if (!response.ok) {
    const body =
      await response
        .json()
        .catch(() => ({}));

    throw new Error(
      body?.detail ??
        `Download failed (HTTP ${response.status}).`,
    );
  }

  const blob =
    await response.blob();

  const url =
    URL.createObjectURL(blob);

  const anchor =
    document.createElement("a");

  anchor.href = url;
  anchor.download =
    filename;

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