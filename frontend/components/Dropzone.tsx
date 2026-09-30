"use client";

import { useCallback, useRef, useState } from "react";
import { Archive, FileImage, FolderOpen, UploadCloud, X } from "lucide-react";

const MAX_FILE_BYTES = 512 * 1024 * 1024;
const MAX_TOTAL_BYTES = 512 * 1024 * 1024;
const MAX_DICOM_FILES = 5000;
const ACCEPTED = [".nii", ".nii.gz", ".dcm", ".dicom", ".ima", ".zip"];

function isNifti(file: File) {
  const name = file.name.toLowerCase();
  return name.endsWith(".nii") || name.endsWith(".nii.gz");
}

function isZip(file: File) {
  return file.name.toLowerCase().endsWith(".zip");
}

function validFile(file: File) {
  const name = file.name.toLowerCase();
  if (ACCEPTED.some((extension) => name.endsWith(extension))) return true;
  return !name.includes(".");
}

function isIgnorableFolderEntry(file: File) {
  const name = file.name.toLowerCase();
  return name === ".ds_store" || name === "thumbs.db" || name.startsWith(".");
}

export default function Dropzone({
  files,
  onFilesChange,
  disabled,
  modalityLabel = "medical imaging",
}: {
  files: File[];
  onFilesChange: (files: File[]) => void;
  disabled?: boolean;
  modalityLabel?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const acceptFiles = useCallback((rawIncoming: File[], fromFolder = false) => {
    setError(null);

    const incoming = fromFolder
      ? rawIncoming.filter((file) => !isIgnorableFolderEntry(file))
      : rawIncoming;

    if (!incoming.length) {
      setError("No readable imaging files were selected.");
      return;
    }

    if (incoming.length > MAX_DICOM_FILES) {
      setError(`This study contains more than ${MAX_DICOM_FILES.toLocaleString()} files. ZIP the DICOM series and upload the ZIP.`);
      return;
    }

    if (incoming.length > 1 && incoming.some((file) => isNifti(file) || isZip(file))) {
      setError("Use one NIfTI volume or one DICOM ZIP at a time. Multiple-file selection is reserved for a DICOM series.");
      return;
    }

    const invalid = incoming.find((file) => !validFile(file));
    if (invalid) {
      setError(`Unsupported file: ${invalid.name}`);
      return;
    }

    const tooLarge = incoming.find((file) => file.size > MAX_FILE_BYTES);
    if (tooLarge) {
      setError(`${tooLarge.name} exceeds the 512 MB file-size limit.`);
      return;
    }

    const totalSize = incoming.reduce((sum, file) => sum + file.size, 0);
    if (totalSize > MAX_TOTAL_BYTES) {
      setError("The selected study exceeds the 512 MB upload limit. ZIP the DICOM series or select a smaller study.");
      return;
    }

    onFilesChange(incoming);
  }, [onFilesChange]);

  return (
    <div className="space-y-2.5">
      <div
        onDragEnter={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          event.preventDefault();
          if (event.currentTarget === event.target) setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (disabled) return;
          acceptFiles(Array.from(event.dataTransfer.files));
        }}
        className={`group relative overflow-hidden rounded-[13px] border border-dashed p-4 transition duration-200 ${
          dragging
            ? "border-teal-300/40 bg-teal-300/[0.07] shadow-[inset_0_0_30px_rgba(85,228,204,0.05)]"
            : "border-white/10 bg-black/10 hover:border-teal-200/20 hover:bg-white/[0.03]"
        } ${disabled ? "pointer-events-none opacity-60" : ""}`}
      >
        <div className="pointer-events-none absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-teal-300/30 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
        <input
          ref={inputRef}
          id="radassist-import-input"
          type="file"
          hidden
          multiple
          accept=".nii,.nii.gz,.dcm,.dicom,.zip"
          onChange={(event) => {
            acceptFiles(Array.from(event.target.files ?? []));
            event.target.value = "";
          }}
        />
        <input
          ref={folderInputRef}
          type="file"
          hidden
          multiple
          // @ts-expect-error -- webkitdirectory is a non-standard browser attribute.
          webkitdirectory=""
          onChange={(event) => {
            acceptFiles(Array.from(event.target.files ?? []), true);
            event.target.value = "";
          }}
        />

        <div className="relative z-10 text-center">
          <div className="mx-auto grid size-10 place-items-center rounded-xl border border-teal-300/15 bg-teal-300/[0.07] text-teal-200 transition duration-200 group-hover:-translate-y-0.5 group-hover:border-teal-200/25">
            <UploadCloud size={19} strokeWidth={1.7} />
          </div>
          <div className="mt-3 font-heading text-[11px] font-semibold text-slate-100">Drop a {modalityLabel} study</div>
          <div className="mx-auto mt-1 max-w-[220px] text-[9px] leading-4 text-slate-500">
            NIfTI, DICOM folder, ZIP series, or extensionless instances
          </div>
          <div className="mt-3 grid grid-cols-2 gap-1.5">
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="flex min-h-[38px] items-center justify-center gap-1.5 rounded-[10px] border border-white/10 bg-white/[0.035] px-2 text-[9px] font-bold text-slate-200 transition hover:-translate-y-px hover:border-white/20 hover:bg-white/[0.06]"
            >
              <FolderOpen size={13} /> File / ZIP
            </button>
            <button
              type="button"
              onClick={() => folderInputRef.current?.click()}
              className="flex min-h-[38px] items-center justify-center gap-1.5 rounded-[10px] border border-white/10 bg-white/[0.018] px-2 text-[9px] font-bold text-slate-400 transition hover:-translate-y-px hover:border-white/20 hover:bg-white/[0.045] hover:text-slate-200"
            >
              <FolderOpen size={13} /> DICOM folder
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-[10px] border border-rose-300/15 bg-rose-300/[0.04] px-3 py-2 text-[9px] leading-4 text-rose-200" role="alert">
          {error}
        </div>
      )}

      {files.length > 0 && (
        <div className="rounded-[12px] border border-white/10 bg-black/10 p-2.5">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="truncate text-[8px] font-bold uppercase tracking-[0.14em] text-slate-500">
              Selected · {(files.reduce((sum, file) => sum + file.size, 0) / 1024 / 1024).toFixed(1)} MB
            </div>
            <button
              type="button"
              onClick={() => onFilesChange([])}
              aria-label="Clear selected files"
              className="grid size-7 place-items-center rounded-lg text-slate-500 transition hover:bg-white/5 hover:text-white"
            >
              <X size={13} />
            </button>
          </div>
          <div className="max-h-28 space-y-1 overflow-auto scroll-thin">
            {files.slice(0, 80).map((file, index) => (
              <div key={`${file.name}-${index}`} className="flex items-center gap-2 text-[9px] text-slate-300">
                {isZip(file) ? <Archive size={12} className="shrink-0 text-slate-500" /> : <FileImage size={12} className="shrink-0 text-slate-500" />}
                <span className="truncate">{file.webkitRelativePath || file.name}</span>
              </div>
            ))}
            {files.length > 80 && <div className="pt-1 text-[9px] text-slate-600">+ {files.length - 80} more files</div>}
          </div>
        </div>
      )}
    </div>
  );
}
