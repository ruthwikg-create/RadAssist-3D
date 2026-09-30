"use client";

import { useEffect, useRef, useState } from "react";
import {
  Enums,
  RenderingEngine,
  imageLoader,
  setVolumesForViewports,
  volumeLoader,
  init as coreInit,
} from "@cornerstonejs/core";
import {
  cornerstoneNiftiImageLoader,
  init as niftiInit,
  createNiftiImageIdsAndCacheMetadata,
} from "@cornerstonejs/nifti-volume-loader";
import {
  addTool,
  Enums as ToolsEnums,
  init as toolsInit,
  PanTool,
  ToolGroupManager,
  WindowLevelTool,
  ZoomTool,
} from "@cornerstonejs/tools";
import type { Types as CSTypes } from "@cornerstonejs/core";
import { Maximize2, Minus, Plus, RotateCcw, X } from "lucide-react";
import DemoMPRViewer from "./DemoMPRViewer";

let initPromise: Promise<void> | null = null;
let toolsRegistered = false;

async function initializeCornerstone() {
  if (!initPromise) {
    initPromise = (async () => {
      await coreInit();
      await toolsInit();
      await niftiInit();
      imageLoader.registerImageLoader("nifti", cornerstoneNiftiImageLoader);
      if (!toolsRegistered) {
        addTool(WindowLevelTool);
        addTool(PanTool);
        addTool(ZoomTool);
        toolsRegistered = true;
      }
    })().catch((error) => {
      initPromise = null;
      throw error;
    });
  }

  return initPromise;
}

function setAllVoi(
  viewports: CSTypes.IVolumeViewport[],
  level: number,
  width: number,
) {
  const safeWidth = Math.max(1, width);
  const lower = level - safeWidth / 2;
  const upper = level + safeWidth / 2;
  viewports.forEach((viewport) => {
    try {
      viewport.setProperties({ voiRange: { lower, upper } });
    } catch {
      // A viewport can briefly be unavailable during load/teardown.
    }
  });
}

export default function CornerstoneMPRViewer({
  volumeUrl,
  caseId,
  isDemo = false,
}: {
  volumeUrl: string;
  caseId: string;
  isDemo?: boolean;
}) {
  const axialRef = useRef<HTMLDivElement>(null);
  const sagittalRef = useRef<HTMLDivElement>(null);
  const coronalRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<RenderingEngine | null>(null);
  const volumeRef = useRef<CSTypes.IImageVolume | null>(null);
  const volumeIdRef = useRef<string | null>(null);
  const viewportsRef = useRef<CSTypes.IVolumeViewport[]>([]);
  const toolGroupIdRef = useRef<string | null>(null);
  const wheelCleanupRef = useRef<(() => void)[]>([]);
  const voiCleanupRef = useRef<(() => void)[]>([]);
  const syncingVoiRef = useRef(false);
  const [status, setStatus] = useState("Initializing MPR");
  const [level, setLevel] = useState(50);
  const [width, setWidth] = useState(400);
  const [sliceIndexes, setSliceIndexes] = useState([0, 0, 0]);
  const [sliceTotals, setSliceTotals] = useState([0, 0, 0]);
  const [fullscreen, setFullscreen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Keep this guard inside the effect so all hooks remain unconditional.
    if (isDemo || !volumeUrl) return undefined;

    let disposed = false;
    const renderingEngineId = `radassist-engine-${caseId}-${Date.now()}`;
    const toolGroupId = `radassist-tools-${caseId}-${Date.now()}`;
    const viewportIds = ["RA_AXIAL", "RA_SAGITTAL", "RA_CORONAL"];
    const viewportElements = [axialRef, sagittalRef, coronalRef];

    function cleanupWheel() {
      wheelCleanupRef.current.splice(0).forEach((cleanup) => cleanup());
    }

    function cleanupVoi() {
      voiCleanupRef.current.splice(0).forEach((cleanup) => cleanup());
    }

    function updateSliceState() {
      const volumeId = volumeIdRef.current;
      const viewports = viewportsRef.current;
      if (!volumeId || !viewports.length) return;

      const nextIndexes = viewports.map((viewport) => {
        try {
          return Math.max(0, viewport.getSliceIndex());
        } catch {
          return 0;
        }
      });
      setSliceIndexes(nextIndexes);
    }

    function installWheelNavigation() {
      cleanupWheel();
      viewportsRef.current.forEach((viewport, index) => {
        const element = viewport.element as HTMLDivElement | undefined;
        if (!element) return;

        const handleWheel = (event: WheelEvent) => {
          event.preventDefault();
          if (disposed) return;
          try {
            viewport.scroll(event.deltaY > 0 ? 1 : -1);
            viewport.render();
            updateSliceState();
          } catch (wheelError) {
            const message = wheelError instanceof Error ? wheelError.message : "Slice navigation failed.";
            setError(message);
          }
        };

        const handleContextMenu = (event: Event) => event.preventDefault();
        element.addEventListener("wheel", handleWheel, { passive: false });
        element.addEventListener("contextmenu", handleContextMenu);
        wheelCleanupRef.current.push(() => {
          element.removeEventListener("wheel", handleWheel);
          element.removeEventListener("contextmenu", handleContextMenu);
        });

        // Give keyboard users a deterministic slice navigation path.
        element.tabIndex = 0;
        const handleKeyDown = (event: KeyboardEvent) => {
          if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
          event.preventDefault();
          try {
            viewport.scroll(event.key === "ArrowDown" ? 1 : -1);
            viewport.render();
            updateSliceState();
          } catch {
            // Keep keyboard navigation best-effort.
          }
        };
        element.addEventListener("keydown", handleKeyDown);
        wheelCleanupRef.current.push(() => element.removeEventListener("keydown", handleKeyDown));

        // Make sure the active viewport is keyboard focusable.
        if (index === 0) element.setAttribute("aria-label", "Axial CT viewport. Use mouse wheel or arrow keys to scroll slices.");
      });
    }

    function installVoiSync() {
      cleanupVoi();
      viewportsRef.current.forEach((viewport) => {
        const element = viewport.element as HTMLDivElement | undefined;
        if (!element) return;

        const onVoiModified = (event: Event) => {
          if (syncingVoiRef.current || disposed) return;
          const detail = (event as CustomEvent<{ range?: { lower: number; upper: number } }>).detail;
          const range = detail?.range;
          if (!range || !Number.isFinite(range.lower) || !Number.isFinite(range.upper)) return;

          syncingVoiRef.current = true;
          try {
            viewportsRef.current.forEach((peer) => {
              peer.setProperties({ voiRange: { lower: range.lower, upper: range.upper } });
            });
          } finally {
            syncingVoiRef.current = false;
          }

          setWidth(Math.max(1, range.upper - range.lower));
          setLevel((range.upper + range.lower) / 2);
        };

        element.addEventListener(Enums.Events.VOI_MODIFIED, onVoiModified);
        voiCleanupRef.current.push(() => element.removeEventListener(Enums.Events.VOI_MODIFIED, onVoiModified));
      });
    }

    async function run() {
      try {
        setError(null);
        setStatus("Initializing Cornerstone…");
        await initializeCornerstone();
        if (disposed) return;

        const imageIds = await createNiftiImageIdsAndCacheMetadata({ url: volumeUrl });
        if (!imageIds?.length) throw new Error("No NIfTI image frames were generated.");
        if (disposed) return;

        const elements = viewportElements.map((ref) => ref.current);
        if (elements.some((element) => !element)) {
          throw new Error("MPR viewport elements were not mounted.");
        }

        const renderingEngine = new RenderingEngine(renderingEngineId);
        engineRef.current = renderingEngine;

        renderingEngine.setViewports(
          elements.map((element, index) => ({
            viewportId: viewportIds[index],
            element: element!,
            type: Enums.ViewportType.ORTHOGRAPHIC,
            defaultOptions: {
              orientation: [
                Enums.OrientationAxis.AXIAL,
                Enums.OrientationAxis.SAGITTAL,
                Enums.OrientationAxis.CORONAL,
              ][index],
              background: [0.01, 0.015, 0.018] as [number, number, number],
            },
          })),
        );

        const volumeId = `cornerstoneStreamingImageVolume:${caseId}`;
        volumeIdRef.current = volumeId;
        setStatus("Loading shared 3D volume…");

        const volume = await volumeLoader.createAndCacheVolume(volumeId, { imageIds });
        volumeRef.current = volume as CSTypes.IImageVolume;
        if (disposed) return;

        await volume.load();
        if (disposed) return;

        await setVolumesForViewports(renderingEngine, [{ volumeId }], viewportIds, true);
        if (disposed) return;

        const nextViewports = viewportIds.map((id) => renderingEngine.getViewport(id)).filter(Boolean) as CSTypes.IVolumeViewport[];
        if (nextViewports.length !== 3) throw new Error("Cornerstone could not create all three orthographic viewports.");
        viewportsRef.current = nextViewports;

        const toolGroup = ToolGroupManager.createToolGroup(toolGroupId);
        if (!toolGroup) throw new Error("Cornerstone could not create the MPR tool group.");

        viewportIds.forEach((viewportId) => toolGroup.addViewport(viewportId, renderingEngineId));
        toolGroup.addTool(WindowLevelTool.toolName);
        toolGroup.addTool(PanTool.toolName);
        toolGroup.addTool(ZoomTool.toolName);

        toolGroup.setToolActive(WindowLevelTool.toolName, {
          bindings: [{ mouseButton: ToolsEnums.MouseBindings.Primary }],
        });
        toolGroup.setToolActive(PanTool.toolName, {
          bindings: [{ mouseButton: ToolsEnums.MouseBindings.Auxiliary }],
        });
        toolGroup.setToolActive(ZoomTool.toolName, {
          bindings: [{ mouseButton: ToolsEnums.MouseBindings.Secondary }],
        });
        toolGroupIdRef.current = toolGroupId;

        setAllVoi(nextViewports, level, width);
        installWheelNavigation();
        installVoiSync();
        const scrollTotals = nextViewports.map((viewport) => {
          try {
            return Math.max(1, viewport.getNumberOfSlices());
          } catch {
            return 1;
          }
        });
        setSliceTotals(scrollTotals);
        updateSliceState();
        renderingEngine.renderViewports(viewportIds);
        setStatus("MPR ready · wheel slice · ↑↓ slice · LMB W/L · MMB pan · RMB zoom");
      } catch (caught) {
        if (!disposed) {
          const message = caught instanceof Error ? caught.message : "MPR initialization failed.";
          setError(message);
          setStatus(message);
        }
      }
    }

    void run();

    const resizeObserver = new ResizeObserver(() => {
      try {
        engineRef.current?.resize(true, true);
        engineRef.current?.renderViewports(viewportIds);
      } catch {
        // Best effort during hot reload/teardown.
      }
    });
    viewportElements.forEach((ref) => {
      if (ref.current) resizeObserver.observe(ref.current);
    });

    return () => {
      disposed = true;
      resizeObserver.disconnect();
      cleanupWheel();
      cleanupVoi();

      if (toolGroupIdRef.current) {
        try {
          ToolGroupManager.destroyToolGroup(toolGroupIdRef.current);
        } catch {
          // Strict mode and hot reload may tear down twice.
        }
        toolGroupIdRef.current = null;
      }

      try {
        volumeRef.current?.removeFromCache();
      } catch {
        // Best effort.
      }
      try {
        volumeRef.current?.destroy();
      } catch {
        // Best effort.
      }
      volumeRef.current = null;
      volumeIdRef.current = null;

      try {
        engineRef.current?.destroy();
      } catch {
        // Best effort.
      }
      engineRef.current = null;
      viewportsRef.current = [];
    };
  }, [caseId, volumeUrl, isDemo]);

  // NOTE: width/level are intentionally not dependencies of the heavy loader
  // effect above in production this would be split; this small follow-up hook
  // applies changes to the already-created viewports without reloading them.
  useEffect(() => {
    if (isDemo) return;
    setAllVoi(viewportsRef.current, level, width);
    viewportsRef.current.forEach((viewport) => {
      try {
        viewport.render();
      } catch {
        // Ignore transient teardown renders.
      }
    });
  }, [level, width, isDemo]);

  useEffect(() => {
    if (!fullscreen) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFullscreen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [fullscreen]);

  // Demo rendering is deliberately outside Cornerstone's NIfTI pipeline.
  // This prevents synthetic cases from allocating large ArrayBuffers in the browser.
  if (isDemo || !volumeUrl) return <DemoMPRViewer />;

  const viewportInfo = [
    ["Axial", sliceIndexes[0], sliceTotals[0]],
    ["Sagittal", sliceIndexes[1], sliceTotals[1]],
    ["Coronal", sliceIndexes[2], sliceTotals[2]],
  ] as const;

  return (
    <section
      className={`glass overflow-hidden rounded-2xl ${fullscreen ? "fixed inset-3 z-[100]" : "relative"}`}
      aria-label="2D multi-planar reconstruction viewer"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-300">2D MPR</div>
          <div className="mt-1 text-[10px] text-slate-500">Axial · sagittal · coronal · one shared volume</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-black/20 px-2 py-1.5">
            <span className="text-[10px] text-slate-500">W</span>
            <button type="button" aria-label="Decrease window width" onClick={() => setWidth((v) => Math.max(10, v - 25))} className="ra-icon-btn"><Minus size={12} /></button>
            <span className="w-12 text-center font-mono text-[10px] text-slate-200">{Math.round(width)}</span>
            <button type="button" aria-label="Increase window width" onClick={() => setWidth((v) => Math.min(4000, v + 25))} className="ra-icon-btn"><Plus size={12} /></button>
          </div>
          <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-black/20 px-2 py-1.5">
            <span className="text-[10px] text-slate-500">L</span>
            <button type="button" aria-label="Decrease window level" onClick={() => setLevel((v) => v - 10)} className="ra-icon-btn"><Minus size={12} /></button>
            <span className="w-12 text-center font-mono text-[10px] text-slate-200">{Math.round(level)}</span>
            <button type="button" aria-label="Increase window level" onClick={() => setLevel((v) => v + 10)} className="ra-icon-btn"><Plus size={12} /></button>
          </div>
          <button type="button" title="Reset W/L" aria-label="Reset W/L" className="ra-icon-btn" onClick={() => { setWidth(400); setLevel(50); }}><RotateCcw size={13} /></button>
          <button type="button" title="Fit images" aria-label="Fit images" className="ra-icon-btn" onClick={() => { viewportsRef.current.forEach((viewport) => { try { viewport.resetCamera(); viewport.render(); } catch {} }); }}><span className="text-[9px] font-bold">FIT</span></button>
          <button type="button" title="Toggle full screen" aria-label="Toggle full screen" className="ra-icon-btn" onClick={() => setFullscreen((v) => !v)}>{fullscreen ? <X size={14} /> : <Maximize2 size={14} />}</button>
        </div>
      </div>

      <div className="grid gap-2 p-2 md:grid-cols-3">
        {viewportInfo.map(([title, sliceIndex, total], index) => {
          const ref = [axialRef, sagittalRef, coronalRef][index];
          return (
            <div key={title} className="relative aspect-square min-h-[280px] overflow-hidden rounded-xl border border-white/10 bg-black">
              <div ref={ref} className="cs-viewport h-full w-full" />
              <div className="pointer-events-none absolute left-3 top-3 z-10 rounded-lg border border-white/10 bg-black/60 px-2 py-1 text-[9px] font-bold uppercase tracking-[0.12em] text-slate-200 backdrop-blur">{title}</div>
              <div className="pointer-events-none absolute bottom-3 right-3 rounded-lg border border-white/10 bg-black/60 px-2 py-1 font-mono text-[9px] text-slate-300 backdrop-blur">
                {total ? `${sliceIndex + 1} / ${total}` : "Loading…"}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 px-4 py-2 text-[9px] text-slate-500">
        <span className={error ? "text-rose-200" : "text-slate-500"}>{status}</span>
        <span>W/L {Math.round(width)} / {Math.round(level)}</span>
      </div>
      {error && (
        <div className="border-t border-rose-300/10 bg-rose-300/[0.04] px-4 py-2 text-[10px] text-rose-200">
          MPR could not complete initialization. The source scan remains available; refresh this study after correcting the source volume if necessary.
        </div>
      )}
    </section>
  );
}
