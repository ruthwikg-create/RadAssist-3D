"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent, WheelEvent as ReactWheelEvent } from "react";
import { Maximize2, Minus, Move, MousePointer2, Plus, RotateCcw, ScanLine, X, ZoomIn } from "lucide-react";

const SIZE = { x: 96, y: 96, z: 64 } as const;
const SPACING = { x: 1.5, y: 1.5, z: 2.0 } as const;

type Axis = keyof typeof SIZE;
type Orientation = "axial" | "sagittal" | "coronal";
type Point = { x: number; y: number };
type ToolMode = "wl" | "pan" | "zoom";
type SliceState = { x: number; y: number; z: number };

const ORIENTATIONS: { id: Orientation; label: string; axis: Axis; xLabel: string; yLabel: string }[] = [
  { id: "axial", label: "Axial", axis: "z", xLabel: "X", yLabel: "Y" },
  { id: "sagittal", label: "Sagittal", axis: "x", xLabel: "Y", yLabel: "Z" },
  { id: "coronal", label: "Coronal", axis: "y", xLabel: "X", yLabel: "Z" },
];

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function indexOf(x: number, y: number, z: number) {
  return z * SIZE.y * SIZE.x + y * SIZE.x + x;
}

function buildSyntheticVolume() {
  const volume = new Int16Array(SIZE.x * SIZE.y * SIZE.z);
  const mask = new Uint8Array(volume.length);

  for (let z = 0; z < SIZE.z; z += 1) {
    for (let y = 0; y < SIZE.y; y += 1) {
      for (let x = 0; x < SIZE.x; x += 1) {
        const bx = (x - 48) / 42;
        const by = (y - 47) / 39;
        const bz = (z - 32) / 29;
        const body = bx * bx + by * by + bz * bz < 1;
        const texture = 6 * Math.sin(x * 0.23 + y * 0.11) + 4 * Math.cos(z * 0.31 + x * 0.07);
        let value = body ? 38 + texture : -1000;

        const kidneyL = ((x - 34) / 8) ** 2 + ((y - 55) / 11) ** 2 + ((z - 35) / 12) ** 2 < 1;
        const kidneyR = ((x - 63) / 8) ** 2 + ((y - 55) / 11) ** 2 + ((z - 35) / 12) ** 2 < 1;
        if (kidneyL || kidneyR) value = 55 + texture * 0.35;

        const spleen = ((x - 62) / 14) ** 2 + ((y - 47) / 10) ** 2 + ((z - 32) / 13) ** 2 <= 1;
        if (spleen) {
          value = 72 + texture * 0.55;
          mask[indexOf(x, y, z)] = 1;
        }

        volume[indexOf(x, y, z)] = Math.round(clamp(value, -1024, 1200));
      }
    }
  }

  return { volume, mask };
}

function planeGeometry(orientation: Orientation) {
  switch (orientation) {
    case "axial":
      return { width: SIZE.x, height: SIZE.y, axis: "z" as Axis };
    case "sagittal":
      return { width: SIZE.y, height: SIZE.z, axis: "x" as Axis };
    default:
      return { width: SIZE.x, height: SIZE.z, axis: "y" as Axis };
  }
}

function voxelAt(orientation: Orientation, u: number, v: number, slices: SliceState) {
  if (orientation === "axial") return { x: u, y: v, z: slices.z };
  if (orientation === "sagittal") return { x: slices.x, y: u, z: v };
  return { x: u, y: slices.y, z: v };
}

function drawSyntheticSlice(
  canvas: HTMLCanvasElement,
  orientation: Orientation,
  slices: SliceState,
  level: number,
  width: number,
  crosshair: SliceState,
  zoom: number,
  pan: Point,
  volume: Int16Array,
  mask: Uint8Array,
) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const rect = canvas.getBoundingClientRect();
  const cssWidth = Math.max(280, rect.width);
  const cssHeight = Math.max(280, rect.height);
  canvas.width = Math.floor(cssWidth * dpr);
  canvas.height = Math.floor(cssHeight * dpr);
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);
  ctx.fillStyle = "#030607";
  ctx.fillRect(0, 0, cssWidth, cssHeight);

  const geometry = planeGeometry(orientation);
  const image = ctx.createImageData(geometry.width, geometry.height);
  const lower = level - Math.max(1, width) / 2;
  const upper = level + Math.max(1, width) / 2;
  const sourceToGray = (value: number) => clamp(((value - lower) / (upper - lower)) * 255, 0, 255);

  for (let v = 0; v < geometry.height; v += 1) {
    for (let u = 0; u < geometry.width; u += 1) {
      const point = voxelAt(orientation, u, v, slices);
      const source = volume[indexOf(point.x, point.y, point.z)];
      const gray = Math.round(sourceToGray(source));
      const i = (v * geometry.width + u) * 4;
      image.data[i] = gray;
      image.data[i + 1] = gray;
      image.data[i + 2] = gray;
      image.data[i + 3] = 255;
    }
  }

  // Render the native-resolution slice to an offscreen canvas, then zoom/pan it
  // into the viewport. This keeps the demo small and deterministic.
  const offscreen = document.createElement("canvas");
  offscreen.width = geometry.width;
  offscreen.height = geometry.height;
  offscreen.getContext("2d")?.putImageData(image, 0, 0);

  ctx.save();
  ctx.translate(cssWidth / 2 + pan.x, cssHeight / 2 + pan.y);
  ctx.scale(zoom, zoom);
  ctx.imageSmoothingEnabled = false;
  const imageScale = Math.min(cssWidth / geometry.width, cssHeight / geometry.height) * 0.92;
  const drawW = geometry.width * imageScale;
  const drawH = geometry.height * imageScale;
  ctx.drawImage(offscreen, -drawW / 2, -drawH / 2, drawW, drawH);

  // Segmentation overlay from the same 3D mask used by the synthetic data.
  ctx.globalAlpha = 0.32;
  ctx.fillStyle = "#39d8c3";
  for (let v = 0; v < geometry.height; v += 1) {
    for (let u = 0; u < geometry.width; u += 1) {
      const point = voxelAt(orientation, u, v, slices);
      if (!mask[indexOf(point.x, point.y, point.z)]) continue;
      const px = -drawW / 2 + (u / geometry.width) * drawW;
      const py = -drawH / 2 + (v / geometry.height) * drawH;
      const cellW = drawW / geometry.width + 0.35;
      const cellH = drawH / geometry.height + 0.35;
      ctx.fillRect(px, py, cellW, cellH);
    }
  }
  ctx.globalAlpha = 1;

  // Anatomical crosshair: for each plane, the two lines represent the other
  // two spatial coordinates from the shared 3D cursor.
  let crossU = 0.5;
  let crossV = 0.5;
  if (orientation === "axial") {
    crossU = crosshair.x / (SIZE.x - 1);
    crossV = crosshair.y / (SIZE.y - 1);
  } else if (orientation === "sagittal") {
    crossU = crosshair.y / (SIZE.y - 1);
    crossV = crosshair.z / (SIZE.z - 1);
  } else {
    crossU = crosshair.x / (SIZE.x - 1);
    crossV = crosshair.z / (SIZE.z - 1);
  }
  const hx = -drawW / 2 + clamp(crossU, 0, 1) * drawW;
  const hy = -drawH / 2 + clamp(crossV, 0, 1) * drawH;
  ctx.strokeStyle = "rgba(218, 247, 243, .45)";
  ctx.lineWidth = 1 / Math.max(zoom, 0.5);
  ctx.setLineDash([4 / Math.max(zoom, 0.5), 4 / Math.max(zoom, 0.5)]);
  ctx.beginPath();
  ctx.moveTo(-drawW / 2, hy);
  ctx.lineTo(drawW / 2, hy);
  ctx.moveTo(hx, -drawH / 2);
  ctx.lineTo(hx, drawH / 2);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "#79eee0";
  ctx.beginPath();
  ctx.arc(hx, hy, 2.5 / Math.max(zoom, 0.7), 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

export default function DemoMPRViewer() {
  const { volume, mask } = useMemo(buildSyntheticVolume, []);
  const canvasRefs = useRef<Record<Orientation, HTMLCanvasElement | null>>({ axial: null, sagittal: null, coronal: null });
  const dragRef = useRef<{ x: number; y: number; mode: ToolMode; orientation: Orientation } | null>(null);
  const [slices, setSlices] = useState<SliceState>({ x: 48, y: 48, z: 32 });
  const [level, setLevel] = useState(50);
  const [width, setWidth] = useState(400);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<Point>({ x: 0, y: 0 });
  const [toolMode, setToolMode] = useState<ToolMode>("wl");
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    const draw = () => {
      ORIENTATIONS.forEach(({ id }) => {
        const canvas = canvasRefs.current[id];
        if (canvas) drawSyntheticSlice(canvas, id, slices, level, width, slices, zoom, pan, volume, mask);
      });
    };
    draw();
    const observer = new ResizeObserver(draw);
    ORIENTATIONS.forEach(({ id }) => {
      const canvas = canvasRefs.current[id];
      if (canvas?.parentElement) observer.observe(canvas.parentElement);
    });
    window.addEventListener("resize", draw);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", draw);
    };
  }, [level, mask, pan, slices, volume, width, zoom]);

  useEffect(() => {
    if (!fullscreen) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFullscreen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullscreen]);

  const reset = () => {
    setSlices({ x: 48, y: 48, z: 32 });
    setLevel(50);
    setWidth(400);
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setToolMode("wl");
  };

  const axisForOrientation = (orientation: Orientation) => planeGeometry(orientation).axis;

  const updateCursorOnClick = (event: ReactMouseEvent<HTMLCanvasElement>, orientation: Orientation) => {
    if (toolMode !== "wl") return;
    const rect = event.currentTarget.getBoundingClientRect();
    const u = clamp((event.clientX - rect.left) / rect.width, 0.01, 0.99);
    const v = clamp((event.clientY - rect.top) / rect.height, 0.01, 0.99);
    setSlices((current) => {
      const next = { ...current };
      if (orientation === "axial") {
        next.x = Math.round(u * (SIZE.x - 1));
        next.y = Math.round(v * (SIZE.y - 1));
      } else if (orientation === "sagittal") {
        next.y = Math.round(u * (SIZE.y - 1));
        next.z = Math.round(v * (SIZE.z - 1));
      } else {
        next.x = Math.round(u * (SIZE.x - 1));
        next.z = Math.round(v * (SIZE.z - 1));
      }
      return next;
    });
  };

  const beginDrag = (event: ReactMouseEvent<HTMLCanvasElement>, orientation: Orientation) => {
    dragRef.current = { x: event.clientX, y: event.clientY, mode: toolMode, orientation };
  };

  const moveDrag = (event: ReactMouseEvent<HTMLCanvasElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    drag.x = event.clientX;
    drag.y = event.clientY;
    if (drag.mode === "pan") {
      setPan((current) => ({ x: clamp(current.x + dx, -260, 260), y: clamp(current.y + dy, -260, 260) }));
      return;
    }
    if (drag.mode === "zoom") {
      setZoom((current) => clamp(current - dy * 0.004, 0.7, 4));
      return;
    }
    setWidth((current) => clamp(current + dx * 2, 10, 4000));
    setLevel((current) => current - dy * 2);
  };

  const onWheel = (event: ReactWheelEvent<HTMLCanvasElement>, orientation: Orientation) => {
    event.preventDefault();
    const axis = axisForOrientation(orientation);
    const delta = event.deltaY > 0 ? 1 : -1;
    if (event.shiftKey || toolMode === "zoom") {
      setZoom((current) => clamp(current - delta * 0.1, 0.7, 4));
      return;
    }
    setSlices((current) => ({
      ...current,
      [axis]: clamp(current[axis] + delta, 0, SIZE[axis] - 1),
    }));
  };

  return (
    <section className={`glass overflow-hidden rounded-2xl ${fullscreen ? "fixed inset-3 z-[100]" : "relative"}`} aria-label="Synthetic multi-planar reconstruction preview">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
        <div>
          <div className="flex items-center gap-2">
            <ScanLine size={14} className="text-teal-300" />
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-300">2D MPR Preview</div>
            <span className="rounded-full border border-amber-200/10 bg-amber-200/5 px-2 py-0.5 text-[8px] font-bold tracking-[0.1em] text-amber-100">SYNTHETIC</span>
          </div>
          <div className="mt-1 text-[10px] text-slate-500">True orthogonal slicing of a small deterministic 3D CT-like test volume · not patient data</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 rounded-xl border border-white/10 bg-black/20 p-1">
            <button type="button" aria-label="Window and level tool" title="W/L tool" className={`ra-icon-btn ${toolMode === "wl" ? "active" : ""}`} onClick={() => setToolMode("wl")}><MousePointer2 size={13} /></button>
            <button type="button" aria-label="Pan tool" title="Pan tool" className={`ra-icon-btn ${toolMode === "pan" ? "active" : ""}`} onClick={() => setToolMode("pan")}><Move size={13} /></button>
            <button type="button" aria-label="Zoom tool" title="Zoom tool" className={`ra-icon-btn ${toolMode === "zoom" ? "active" : ""}`} onClick={() => setToolMode("zoom")}><ZoomIn size={13} /></button>
          </div>
          <div className="flex items-center gap-1 rounded-xl border border-white/10 bg-black/20 p-1">
            <button type="button" aria-label="Decrease window width" className="ra-icon-btn" onClick={() => setWidth((v) => clamp(v - 25, 10, 4000))}><Minus size={12} /></button>
            <span className="w-14 text-center font-mono text-[10px] text-slate-300">W {Math.round(width)}</span>
            <button type="button" aria-label="Increase window width" className="ra-icon-btn" onClick={() => setWidth((v) => clamp(v + 25, 10, 4000))}><Plus size={12} /></button>
          </div>
          <div className="flex items-center gap-1 rounded-xl border border-white/10 bg-black/20 p-1">
            <button type="button" aria-label="Decrease window level" className="ra-icon-btn" onClick={() => setLevel((v) => v - 10)}><Minus size={12} /></button>
            <span className="w-14 text-center font-mono text-[10px] text-slate-300">L {Math.round(level)}</span>
            <button type="button" aria-label="Increase window level" className="ra-icon-btn" onClick={() => setLevel((v) => v + 10)}><Plus size={12} /></button>
          </div>
          <button type="button" title="Reset demo MPR" aria-label="Reset demo MPR" className="ra-icon-btn" onClick={reset}><RotateCcw size={13} /></button>
          <button type="button" title={fullscreen ? "Exit full-screen" : "Enter full-screen"} aria-label="Toggle full-screen" className="ra-icon-btn" onClick={() => setFullscreen((v) => !v)}>{fullscreen ? <X size={14} /> : <Maximize2 size={14} />}</button>
        </div>
      </div>

      <div className="grid gap-2 p-2 md:grid-cols-3">
        {ORIENTATIONS.map(({ id, label, axis, xLabel, yLabel }) => {
          const axisIndex = slices[axis] + 1;
          const axisTotal = SIZE[axis];
          return (
            <div key={id} className="relative aspect-square overflow-hidden rounded-xl border border-white/10 bg-black/90">
              <canvas
                ref={(element) => { canvasRefs.current[id] = element; }}
                onClick={(event) => updateCursorOnClick(event, id)}
                onWheel={(event) => onWheel(event, id)}
                onMouseDown={(event) => beginDrag(event, id)}
                onMouseMove={moveDrag}
                onMouseUp={() => { dragRef.current = null; }}
                onMouseLeave={() => { dragRef.current = null; }}
                className="block h-full w-full"
                aria-label={`${label} synthetic MPR viewport`}
              />
              <div className="pointer-events-none absolute left-3 top-3 z-10 flex items-center gap-2 rounded-lg border border-white/10 bg-black/65 px-2 py-1.5 backdrop-blur">
                <span className="grid size-5 place-items-center rounded bg-teal-300/10 font-mono text-[9px] text-teal-200">{axis.toUpperCase()}</span>
                <span className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-200">{label}</span>
              </div>
              <div className="pointer-events-none absolute bottom-3 left-3 rounded-lg border border-white/10 bg-black/65 px-2 py-1 font-mono text-[9px] text-slate-300 backdrop-blur">{axisIndex} / {axisTotal} · {SPACING[axis].toFixed(2)} mm</div>
              <div className="pointer-events-none absolute bottom-3 right-3 rounded-lg border border-white/10 bg-black/65 px-2 py-1 font-mono text-[9px] text-slate-500 backdrop-blur">{xLabel}→ · {yLabel}↓</div>
            </div>
          );
        })}
      </div>

      <div className="border-t border-white/10 px-4 py-3">
        <div className="mb-2 grid gap-2 text-[9px] text-slate-500 sm:grid-cols-3">
          {(Object.keys(SIZE) as Axis[]).map((axis) => (
            <label key={axis} className="flex items-center gap-2">
              <span className="w-8 font-mono text-slate-400">{axis.toUpperCase()}</span>
              <input
                type="range"
                min={0}
                max={SIZE[axis] - 1}
                value={slices[axis]}
                aria-label={`${axis.toUpperCase()} slice position`}
                onChange={(event) => setSlices((current) => ({ ...current, [axis]: Number(event.target.value) }))}
                className="range-teal flex-1"
              />
              <span className="w-14 text-right font-mono text-slate-300">{slices[axis] + 1}/{SIZE[axis]}</span>
            </label>
          ))}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 text-[9px] text-slate-500">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1"><MousePointer2 size={12} /> W/L + cursor</span>
            <span className="inline-flex items-center gap-1"><Move size={12} /> Pan</span>
            <span className="inline-flex items-center gap-1"><ZoomIn size={12} /> Zoom</span>
            <span>Wheel · slice</span>
          </div>
          <div className="font-mono text-[10px] text-slate-300">X {slices.x + 1} · Y {slices.y + 1} · Z {slices.z + 1} · W/L {Math.round(width)} / {Math.round(level)}</div>
        </div>
      </div>
    </section>
  );
}
