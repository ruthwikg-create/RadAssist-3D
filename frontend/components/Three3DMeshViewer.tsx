"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Maximize2,
  Minimize2,
  RotateCcw,
  Eye,
  EyeOff,
  Grid3X3,
} from "lucide-react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import type {
  CaseResult,
  LabelMeshData,
  MeshData,
} from "@/lib/types";

type Props = {
  mesh: MeshData;
  labelMeshes?: Record<string, LabelMeshData>;
  meshDiagnostics?: Record<string, string>;
  target?: CaseResult["target"];
};

type Surface = {
  id: string;
  label: number;
  name: string;
  mesh: MeshData;
  color: number;
};

type SurfaceState = {
  visible: boolean;
  opacity: number;
};

const COLORS: Record<string, number> = {
  spleen: 0x5eead4,
  heart1: 0xff5c5c,
  heart2: 0xffd166,
  heart3: 0x5ca9ff,
  prostate1: 0xff8a65ff,
  prostate2: 0x4dd9c0,
};

function usable(mesh?: MeshData): boolean {
  return Boolean(
    mesh &&
      Array.isArray(mesh.vertices) &&
      Array.isArray(mesh.faces) &&
      mesh.vertices.length >= 3 &&
      mesh.faces.length >= 1,
  );
}

function colorFor(target: string | undefined, label: number) {
  if (target === "heart") {
    return (
      COLORS[`heart${label}`] ??
      COLORS.spleen
    );
  }

  if (target === "prostate") {
    return (
      COLORS[`prostate${label}`] ??
      COLORS.spleen
    );
  }

  return COLORS.spleen;
}

function getSurfaces(
  target: string | undefined,
  labelMeshes: Record<string, LabelMeshData> | undefined,
  fallback: MeshData,
): Surface[] {
  const result: Surface[] = [];

  if (labelMeshes) {
    for (const [id, value] of Object.entries(labelMeshes)) {
      if (!usable(value)) continue;

      result.push({
        id,
        label: value.label,
        name: value.name,
        mesh: value,
        color: colorFor(target, value.label),
      });
    }
  }

  if (result.length > 0) {
    return result;
  }

  if (usable(fallback)) {
    return [
      {
        id: "combined",
        label: 1,
        name: "Segmentation surface",
        mesh: fallback,
        color: colorFor(target, 1),
      },
    ];
  }

  return [];
}

function makeGeometry(mesh: MeshData) {
  const geometry = new THREE.BufferGeometry();

  // Three.js indexed geometry requires the position array and face indices
  // to remain parallel. Do not remove individual invalid vertices while
  // retaining their original indices.
  const vertices: number[] = [];
  const validVertex: boolean[] = [];

  for (const vertex of mesh.vertices) {
    const x = Number(vertex?.[0]);
    const y = Number(vertex?.[1]);
    const z = Number(vertex?.[2]);
    const valid =
      Number.isFinite(x) &&
      Number.isFinite(y) &&
      Number.isFinite(z);

    validVertex.push(valid);
    vertices.push(
      valid ? x : 0,
      valid ? y : 0,
      valid ? z : 0,
    );
  }

  const indices: number[] = [];

  for (const face of mesh.faces) {
    const a = Number(face?.[0]);
    const b = Number(face?.[1]);
    const c = Number(face?.[2]);

    if (
      Number.isInteger(a) &&
      Number.isInteger(b) &&
      Number.isInteger(c) &&
      a >= 0 &&
      b >= 0 &&
      c >= 0 &&
      a < mesh.vertices.length &&
      b < mesh.vertices.length &&
      c < mesh.vertices.length &&
      validVertex[a] &&
      validVertex[b] &&
      validVertex[c]
    ) {
      indices.push(a, b, c);
    }
  }

  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(vertices, 3),
  );

  geometry.setIndex(indices);

  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();

  return geometry;
}

export default function ThreeDMeshViewer({
  mesh,
  labelMeshes,
  meshDiagnostics,
  target,
}: Props) {
  const containerRef =
    useRef<HTMLDivElement | null>(null);

  const rendererRef =
    useRef<THREE.WebGLRenderer | null>(null);

  const cameraRef =
    useRef<THREE.PerspectiveCamera | null>(null);

  const controlsRef =
    useRef<OrbitControls | null>(null);

  const groupRef =
    useRef<THREE.Group | null>(null);

  const initialCameraRef =
    useRef<{
      position: THREE.Vector3;
      target: THREE.Vector3;
    } | null>(null);

  const animationRef =
    useRef<number | null>(null);

  const objectsRef =
    useRef<
      Map<
        string,
        THREE.Mesh<
          THREE.BufferGeometry,
          THREE.MeshStandardMaterial
        >
      >
    >(new Map());

  const surfaces = useMemo(
    () =>
      getSurfaces(
        target,
        labelMeshes,
        mesh,
      ),
    [target, labelMeshes, mesh],
  );

  const [states, setStates] =
    useState<Record<string, SurfaceState>>(
      {},
    );

  const [wireframe, setWireframe] =
    useState(false);

  const [showAxes, setShowAxes] =
    useState(true);

  const [showGrid, setShowGrid] =
    useState(true);

  const [fullscreen, setFullscreen] =
    useState(false);
  const [clipEnabled, setClipEnabled] =
    useState(false);
  const [clipPosition, setClipPosition] =
    useState(0);
  const clippingPlaneRef =
    useRef(new THREE.Plane(new THREE.Vector3(1, 0, 0), 0));

  const [error, setError] =
    useState<string | null>(null);

  useEffect(() => {
    setStates((previous) => {
      const next: Record<
        string,
        SurfaceState
      > = {};

      for (const surface of surfaces) {
        next[surface.id] =
          previous[surface.id] ?? {
            visible: true,
            opacity: 0.9,
          };
      }

      return next;
    });
  }, [surfaces, clipPosition]);

  useEffect(() => {
    const container =
      containerRef.current;

    if (!container || surfaces.length === 0) {
      return;
    }

    let renderer: THREE.WebGLRenderer;

    try {
      renderer =
        new THREE.WebGLRenderer({
          antialias: true,
          alpha: false,
          powerPreference: "high-performance",
        });
    } catch {
      setError(
        "WebGL could not be initialized.",
      );
      return;
    }

    setError(null);

    renderer.setPixelRatio(
      Math.min(
        window.devicePixelRatio || 1,
        2,
      ),
    );

    renderer.setClearColor(
      0x07131a,
      1,
    );

    renderer.outputColorSpace =
      THREE.SRGBColorSpace;
    renderer.localClippingEnabled = true;
    renderer.clippingPlanes = clipEnabled ? [clippingPlaneRef.current] : [];

    const width =
      Math.max(
        container.clientWidth,
        1,
      );

    const height =
      Math.max(
        container.clientHeight,
        1,
      );

    renderer.setSize(
      width,
      height,
      false,
    );

    renderer.domElement.style.display =
      "block";

    renderer.domElement.style.width =
      "100%";

    renderer.domElement.style.height =
      "100%";

    container.innerHTML = "";

    container.appendChild(
      renderer.domElement,
    );

    const scene =
      new THREE.Scene();

    scene.background =
      new THREE.Color(0x07131a);

    const camera =
      new THREE.PerspectiveCamera(
        45,
        width / height,
        0.01,
        10000,
      );

    camera.position.set(
      80,
      55,
      90,
    );

    const controls =
      new OrbitControls(
        camera,
        renderer.domElement,
      );

    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.target.set(0, 0, 0);

    const ambient =
      new THREE.AmbientLight(
        0xffffff,
        2.2,
      );

    scene.add(ambient);

    const key =
      new THREE.DirectionalLight(
        0xffffff,
        3.5,
      );

    key.position.set(
      100,
      150,
      200,
    );

    scene.add(key);

    const fill =
      new THREE.DirectionalLight(
        0x9edcff,
        1.8,
      );

    fill.position.set(
      -100,
      -80,
      120,
    );

    scene.add(fill);

    const group =
      new THREE.Group();

    scene.add(group);

    const objects =
      new Map<
        string,
        THREE.Mesh<
          THREE.BufferGeometry,
          THREE.MeshStandardMaterial
        >
      >();

    const combinedBox =
      new THREE.Box3();

    let hasBounds = false;

    for (const surface of surfaces) {
      const geometry =
        makeGeometry(
          surface.mesh,
        );

      if (
        !geometry.attributes
          .position ||
        geometry.index === null
      ) {
        geometry.dispose();
        continue;
      }

      if (geometry.boundingBox) {
        combinedBox.union(
          geometry.boundingBox,
        );
        hasBounds = true;
      }

      const material =
        new THREE.MeshStandardMaterial({
          color: surface.color,
          roughness: 0.42,
          metalness: 0.02,
          transparent: false,
          opacity: 1,
          side: THREE.DoubleSide,
          wireframe: false,
          depthWrite: true,
          depthTest: true,
        });

      const object =
        new THREE.Mesh(
          geometry,
          material,
        );

      object.visible = true;

      group.add(object);
      objects.set(
        surface.id,
        object,
      );
    }

    if (!hasBounds || objects.size === 0) {
      setError(
        "The supplied mesh contains no renderable geometry.",
      );

      renderer.dispose();

      return;
    }

    const center =
      new THREE.Vector3();

    const size =
      new THREE.Vector3();

    combinedBox.getCenter(center);
    combinedBox.getSize(size);

    group.position.set(
      -center.x,
      -center.y,
      -center.z,
    );

    const maxDimension =
      Math.max(
        size.x,
        size.y,
        size.z,
        1,
      );

    const distance =
      maxDimension * 2.4;

    camera.position.set(
      distance * 0.8,
      distance * 0.55,
      distance,
    );

    camera.near =
      Math.max(
        maxDimension / 1000,
        0.01,
      );

    camera.far =
      Math.max(
        maxDimension * 20,
        1000,
      );

    camera.lookAt(0, 0, 0);
    clippingPlaneRef.current.constant = clipPosition * maxDimension;

    controls.target.set(
      0,
      0,
      0,
    );

    controls.update();

    initialCameraRef.current = {
      position:
        camera.position.clone(),
      target:
        controls.target.clone(),
    };

    const axes =
      new THREE.AxesHelper(
        Math.max(
          maxDimension * 0.8,
          20,
        ),
      );

    axes.name =
      "radassist-axes";

    scene.add(axes);

    const grid =
      new THREE.GridHelper(
        Math.max(
          maxDimension * 3,
          100,
        ),
        20,
      );

    grid.name =
      "radassist-grid";

    grid.position.y =
      -maxDimension * 0.8;

    scene.add(grid);

    rendererRef.current =
      renderer;

    cameraRef.current =
      camera;

    controlsRef.current =
      controls;

    groupRef.current =
      group;

    objectsRef.current =
      objects;

    const resizeObserver =
      new ResizeObserver(() => {
        const w =
          Math.max(
            container.clientWidth,
            1,
          );

        const h =
          Math.max(
            container.clientHeight,
            1,
          );

        camera.aspect =
          w / h;

        camera.updateProjectionMatrix();

        renderer.setSize(
          w,
          h,
          false,
        );
      });

    resizeObserver.observe(
      container,
    );

    const render =
      () => {
        controls.update();

        renderer.render(
          scene,
          camera,
        );

        animationRef.current =
          requestAnimationFrame(
            render,
          );
      };

    render();

    return () => {
      if (
        animationRef.current !==
        null
      ) {
        cancelAnimationFrame(
          animationRef.current,
        );
      }

      resizeObserver.disconnect();

      controls.dispose();

      for (
        const object of objects.values()
      ) {
        object.geometry.dispose();
        object.material.dispose();
      }

      renderer.dispose();

      if (
        renderer.domElement.parentElement ===
        container
      ) {
        container.removeChild(
          renderer.domElement,
        );
      }

      objects.clear();

      rendererRef.current = null;
      cameraRef.current = null;
      controlsRef.current = null;
      groupRef.current = null;
      objectsRef.current.clear();
    };
  }, [surfaces]);

  useEffect(() => {
    clippingPlaneRef.current.constant =
      clipPosition * Math.max(
        1,
        groupRef.current?.children.reduce((max, child) => {
          const box = new THREE.Box3().setFromObject(child);
          return Math.max(max, box.getSize(new THREE.Vector3()).length());
        }, 1) ?? 1,
      );
    if (rendererRef.current) {
      rendererRef.current.clippingPlanes = clipEnabled
        ? [clippingPlaneRef.current]
        : [];
    }
    for (
      const [
        id,
        object,
      ] of objectsRef.current
    ) {
      const state =
        states[id];

      if (!state) continue;

      object.visible =
        state.visible;

      object.material.opacity =
        state.opacity;

      object.material.transparent =
        state.opacity < 1;

      object.material.wireframe =
        wireframe;
    }
  }, [states, wireframe, clipPosition, clipEnabled]);

  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;
    const scene = group.parent;
    if (!scene) return;
    const axes = scene.getObjectByName("radassist-axes");
    const grid = scene.getObjectByName("radassist-grid");
    if (axes) axes.visible = showAxes;
    if (grid) grid.visible = showGrid;
  }, [showAxes, showGrid]);

  const toggleSurface =
    (id: string) => {
      setStates((current) => ({
        ...current,
        [id]: {
          ...(current[id] ?? {
            visible: true,
            opacity: 0.9,
          }),
          visible:
            !(
              current[id]
                ?.visible ?? true
            ),
        },
      }));
    };

  const resetCamera =
    () => {
      const camera =
        cameraRef.current;

      const controls =
        controlsRef.current;

      const initial =
        initialCameraRef.current;

      if (
        !camera ||
        !controls ||
        !initial
      ) {
        return;
      }

      camera.position.copy(
        initial.position,
      );

      controls.target.copy(
        initial.target,
      );

      controls.update();
    };

  const toggleFullscreen =
    async () => {
      const element =
        containerRef.current
          ?.parentElement;

      if (!element) return;

      try {
        if (
          document.fullscreenElement
        ) {
          await document.exitFullscreen();
        } else {
          await element.requestFullscreen();
        }
        setFullscreen(Boolean(document.fullscreenElement));
      } catch {
        // Ignore fullscreen errors.
      }
    };

  return (
    <div className="flex min-h-[520px] flex-col bg-[#07131a] text-slate-200">
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-2">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em]">
            3D Surface
          </div>

          <div className="mt-0.5 text-[9px] text-slate-500">
            Orbit · pan · zoom · anatomical surface rendering
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() =>
              setWireframe(
                (value) => !value,
              )
            }
            className="rounded-md border border-white/10 px-2 py-1 text-[9px]"
          >
            Wire
          </button>

          <button
            type="button"
            onClick={() =>
              setShowAxes(
                (value) => !value,
              )
            }
            className={`rounded-md border p-1.5 ${
              showAxes
                ? "border-cyan-400/40 text-cyan-300"
                : "border-white/10 text-slate-500"
            }`}
            title="Toggle axes"
          >
            XYZ
          </button>

          <button
            type="button"
            onClick={() =>
              setShowGrid(
                (value) => !value,
              )
            }
            className={`rounded-md border p-1.5 ${
              showGrid
                ? "border-cyan-400/40 text-cyan-300"
                : "border-white/10 text-slate-500"
            }`}
            title="Toggle grid"
          >
            <Grid3X3 size={13} />
          </button>

          <button
            type="button"
            onClick={() => setClipEnabled((value) => !value)}
            className={`rounded-md border px-2 py-1 text-[9px] ${clipEnabled ? "border-cyan-400/40 text-cyan-300" : "border-white/10 text-slate-400"}`}
            title="Toggle clipping plane"
          >
            Clip
          </button>

          <button
            type="button"
            onClick={resetCamera}
            className="rounded-md border border-white/10 p-1.5 text-slate-400"
            title="Reset camera"
          >
            <RotateCcw size={13} />
          </button>

          <button
            type="button"
            onClick={toggleFullscreen}
            className="rounded-md border border-white/10 p-1.5 text-slate-400"
            title="Fullscreen"
          >
            {fullscreen ? (
              <Minimize2 size={13} />
            ) : (
              <Maximize2 size={13} />
            )}
          </button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_190px]">
        <div
          ref={containerRef}
          className="relative min-h-[430px] overflow-hidden"
        >
          {error && (
            <div className="absolute inset-0 z-10 flex items-center justify-center p-6">
              <div className="max-w-md rounded-lg border border-red-400/20 bg-red-950/40 p-4 text-center text-xs text-red-200">
                <div>{error}</div>
                {diagnosticText ? (
                  <div className="mt-2 break-words text-[9px] text-red-200/70">
                    {diagnosticText}
                  </div>
                ) : null}
              </div>
            </div>
          )}
        </div>

        <aside className="border-t border-white/10 bg-black/20 p-3 lg:border-l lg:border-t-0">
          {clipEnabled && (
            <div className="mb-3 rounded-lg border border-cyan-300/10 bg-cyan-300/[0.03] p-2.5">
              <div className="flex items-center justify-between text-[9px] uppercase tracking-[0.12em] text-slate-500">
                <span>Clipping plane</span>
                <span className="font-mono text-cyan-200">{clipPosition.toFixed(2)}</span>
              </div>
              <input
                aria-label="3D clipping plane position"
                type="range"
                min="-1"
                max="1"
                step="0.01"
                value={clipPosition}
                onChange={(event) => setClipPosition(Number(event.target.value))}
                className="mt-2 w-full accent-cyan-400"
              />
            </div>
          )}
          <div className="mb-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              Structures
            </div>

            <div className="mt-1 text-[9px] text-slate-600">
              {surfaces.reduce(
                (sum, item) =>
                  sum +
                  item.mesh.vertex_count,
                0,
              ).toLocaleString()}{" "}
              vertices ·{" "}
              {surfaces.reduce(
                (sum, item) =>
                  sum +
                  item.mesh.face_count,
                0,
              ).toLocaleString()}{" "}
              triangles
            </div>
          </div>

          <div className="space-y-3">
            {surfaces.map(
              (surface) => {
                const state =
                  states[
                    surface.id
                  ] ?? {
                    visible: true,
                    opacity: 0.9,
                  };

                return (
                  <div
                    key={
                      surface.id
                    }
                    className="rounded-lg border border-white/10 bg-white/[0.025] p-2.5"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{
                          backgroundColor:
                            `#${surface.color
                              .toString(16)
                              .padStart(
                                6,
                                "0",
                              )}`,
                        }}
                      />

                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[11px] font-medium">
                          {surface.name}
                        </div>

                        <div className="text-[9px] text-slate-500">
                          {surface.mesh.vertex_count.toLocaleString()}{" "}
                          vertices ·{" "}
                          {surface.mesh.face_count.toLocaleString()}{" "}
                          triangles
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() =>
                          toggleSurface(
                            surface.id,
                          )
                        }
                        className="text-slate-500"
                        title={
                          state.visible
                            ? "Hide"
                            : "Show"
                        }
                      >
                        {state.visible ? (
                          <Eye size={13} />
                        ) : (
                          <EyeOff
                            size={13}
                          />
                        )}
                      </button>
                    </div>

                    <div className="mt-3">
                      <input
                        type="range"
                        min="0.15"
                        max="1"
                        step="0.05"
                        value={
                          state.opacity
                        }
                        onChange={(event) =>
                          setStates(
                            (current) => ({
                              ...current,
                              [surface.id]: {
                                ...(
                                  current[
                                    surface.id
                                  ] ?? {
                                    visible:
                                      true,
                                    opacity:
                                      0.9,
                                  }
                                ),
                                opacity:
                                  Number(
                                    event
                                      .target
                                      .value,
                                  ),
                              },
                            }),
                          )
                        }
                        className="w-full accent-cyan-400"
                      />
                    </div>
                  </div>
                );
              },
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}