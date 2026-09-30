from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    ROOT / "backend" / "main.py",
    ROOT / "backend" / "pipeline.py",
    ROOT / "backend" / "case_store.py",
    ROOT / "backend" / "requirements.txt",
    ROOT / "frontend" / "package.json",
    ROOT / "frontend" / "app" / "layout.tsx",
    ROOT / "frontend" / "app" / "globals.css",
    ROOT / "frontend" / "components" / "ScanWorkspace.tsx",
    ROOT / "frontend" / "components" / "Dropzone.tsx",
    ROOT / "frontend" / "components" / "CornerstoneMPRViewer.tsx",
    ROOT / "frontend" / "components" / "DemoMPRViewer.tsx",
    ROOT / "frontend" / "components" / "Three3DMeshViewer.tsx",
    ROOT / "frontend" / "components" / "MetricsPanel.tsx",
    ROOT / "frontend" / "components" / "ViewerErrorBoundary.tsx",
    ROOT / "frontend" / "lib" / "api.ts",
    ROOT / "frontend" / "lib" / "types.ts",
    ROOT / "model_training" / "train_spleen_segresnet.py",
    ROOT / "start-radassist.cmd",
    ROOT / "VERIFY-LOCAL.cmd",
]

missing = [str(p.relative_to(ROOT)) for p in REQUIRED if not p.exists()]
if missing:
    print("Missing required files:")
    print("\n".join(missing))
    raise SystemExit(1)

py_files = sorted((ROOT / "backend").glob("*.py")) + [ROOT / "model_training" / "train_spleen_segresnet.py"]
subprocess.run([sys.executable, "-m", "py_compile", *map(str, py_files)], check=True)

package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
assert package["scripts"]["build"] == "next build --webpack"
assert package["scripts"]["dev"] == "next dev --webpack"
for dependency in ("@cornerstonejs/core", "@cornerstonejs/tools", "@cornerstonejs/nifti-volume-loader", "three", "lucide-react"):
    assert dependency in package["dependencies"], dependency

cornerstone = (ROOT / "frontend" / "components" / "CornerstoneMPRViewer.tsx").read_text(encoding="utf-8")
scan = (ROOT / "frontend" / "components" / "ScanWorkspace.tsx").read_text(encoding="utf-8")
demo = (ROOT / "frontend" / "components" / "DemoMPRViewer.tsx").read_text(encoding="utf-8")
three = (ROOT / "frontend" / "components" / "Three3DMeshViewer.tsx").read_text(encoding="utf-8")
api = (ROOT / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")
pipeline = (ROOT / "backend" / "pipeline.py").read_text(encoding="utf-8")
css = (ROOT / "frontend" / "app" / "globals.css").read_text(encoding="utf-8")
layout = (ROOT / "frontend" / "app" / "layout.tsx").read_text(encoding="utf-8")
assert "MPR" in scan and "3D Surface" in scan and "Quantification" in scan

# Demo path must never enter Cornerstone's NIfTI volume loader.
assert '{result.is_demo ? (' in scan and '<DemoMPRViewer />' in scan
assert 'if (isDemo || !volumeUrl) return <DemoMPRViewer />;' in cornerstone
assert 'createNiftiImageIdsAndCacheMetadata' in cornerstone
assert 'getSliceIndex()' in cornerstone
assert 'getNumberOfSlices()' in cornerstone
assert 'imageLoader.registerImageLoader("nifti", cornerstoneNiftiImageLoader)' in cornerstone
assert 'await toolsInit();' in cornerstone
assert 'viewport.scroll(' in cornerstone
assert 'StackScrollMouseWheelTool' not in cornerstone
assert 'if (isDemo || !volumeUrl) return undefined;' in cornerstone
assert 'cache.purgeCache' not in cornerstone
assert 'preview.nii.gz' not in pipeline

# Demo viewer has deterministic, browser-only controls.
for token in ('onWheel', 'onMouseDown', 'setToolMode', 'fullscreen', 'setSlices'):
    assert token in demo, token

# 3D controls and guarded mesh handling.
for token in ('OrbitControls', 'WebGL is unavailable', 'setOpacity', 'setWireframe', 'setShowAxes', 'fullscreen'):
    assert token in three, token

# API has resilient local demo behavior and absolute URL handling.
for token in ('API_BASE_URL', 'createDemoCase', 'buildLocalDemoCase', 'absoluteUrl'):
    assert token in api, token
assert 'fetch(`${API_BASE_URL}/api/v1/demo' not in api

# Backend memory/security/measurement safeguards.
for token in ('SW_CPU_STITCH', 'sw_device', 'MESH_MAX_VERTICES', 'MAX_BROWSER_PREVIEW_DIM', 'write_sanitized_nifti', '_safe_extract_zip'):
    assert token in pipeline, token
assert 'MAX_BROWSER_PREVIEW_DIM = int(os.getenv("RADASSIST_MAX_BROWSER_PREVIEW_DIM", "128"))' in pipeline
assert 'candidates: dict[str, tuple[Path, list[str]]]' in pipeline

# Design-system checks.
assert '@fontsource-variable/figtree' in layout and '@fontsource-variable/noto-sans' in layout
assert 'Figtree Variable' in css and 'Noto Sans Variable' in css
assert '.ra-icon-btn.active' in css
assert 'prefers-reduced-motion' in css

# Parse every TS/TSX file for syntax using the globally installed TypeScript compiler.
node_script = r'''
const fs = require('fs');
const path = require('path');
const root = process.argv[1];
const tsModulePath = (() => {
  try { return require.resolve('typescript', { paths: [path.join(root, 'frontend')] }); }
  catch { return require.resolve('typescript'); }
})();
const ts = require(tsModulePath);
function walk(dir) {
  const out = [];
  for (const name of fs.readdirSync(dir)) {
    if (name === 'node_modules' || name === '.next') continue;
    const full = path.join(dir, name);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) out.push(...walk(full));
    else if (/\.(ts|tsx)$/.test(name) && !name.endsWith('.d.ts')) out.push(full);
  }
  return out;
}
let failed = 0;
for (const file of walk(path.join(root, 'frontend'))) {
  const source = fs.readFileSync(file, 'utf8');
  const scriptKind = file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, scriptKind);
  const diagnostics = sf.parseDiagnostics || [];
  if (diagnostics.length) {
    failed++;
    for (const d of diagnostics) console.error(`${file}: ${ts.flattenDiagnosticMessageText(d.messageText, '\n')}`);
  }
}
process.exit(failed ? 1 : 0);
'''
subprocess.run(["node", "-e", node_script, str(ROOT)], check=True)

node_modules = ROOT / "frontend" / "node_modules"
if node_modules.exists():
    # Windows exposes npm through npm.cmd; Python's subprocess does not always
    # resolve the bare "npm" command even when it works in an interactive CMD.
    npm_exe = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm_exe:
        raise RuntimeError(
            "npm was not found on PATH. Open a new Command Prompt after installing Node.js."
        )
    print(f"Using npm executable: {npm_exe}")
    subprocess.run([npm_exe, "run", "lint"], cwd=ROOT / "frontend", check=True)
    subprocess.run([npm_exe, "run", "build"], cwd=ROOT / "frontend", check=True)
else:
    print("Frontend node_modules not present in verification environment; skipped npm lint/build.")

print("RadAssist 3D comprehensive static/source verification passed.")

# Medical-QC/provenance checks.
for token in ("measurement_quality", "model_provenance", "hu_calibrated", "centroid_mm", "surface_area_cm2", "mesh_volume_cm3", "volume_difference_pct"):
    assert token in pipeline, token
for token in ("API_BASE_URL", "MPR", "3D Surface", "Quantification", "QA"):
    assert token in scan, token
assert "AI checkpoint required" in scan
print("Medical-QC source checks passed.")
