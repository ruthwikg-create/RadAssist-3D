"use client";

import { useEffect, useState } from "react";
import { Database, ChevronDown, ChevronUp } from "lucide-react";
import { caseDicomMetadataUrl } from "@/lib/api";

type Props = { caseId: string; enabled: boolean };

export default function DicomMetadataPanel({ caseId, enabled }: Props) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    fetch(caseDicomMetadataUrl(caseId), { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("DICOM metadata is unavailable.");
        return response.json();
      })
      .then((value) => {
        if (!cancelled) setData(value);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Metadata request failed.");
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, enabled]);

  if (!enabled) return null;

  return (
    <section className="ra-inspector-card p-3">
      <button type="button" onClick={() => setOpen((value) => !value)} className="flex w-full items-center gap-2 text-left">
        <Database size={14} className="text-cyan-300" />
        <span className="ra-section-label flex-1">DICOM metadata</span>
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>
      {open && (
        <div className="mt-3 space-y-2 text-[9px]">
          {error ? <div className="text-amber-200">{error}</div> : null}
          {data ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                <div><span className="text-slate-600">Instances</span><strong className="block text-slate-200">{String(data.instance_count ?? "—")}</strong></div>
                <div><span className="text-slate-600">Series</span><strong className="block text-slate-200">{String(data.series_count ?? "—")}</strong></div>
                <div><span className="text-slate-600">Modality</span><strong className="block text-slate-200">{Array.isArray(data.modalities) ? data.modalities.join(", ") : "—"}</strong></div>
                <div><span className="text-slate-600">De-identification</span><strong className="block text-teal-200">Metadata sanitized</strong></div>
              </div>
              <div className="rounded-lg border border-amber-300/10 bg-amber-300/[0.03] p-2 leading-4 text-amber-100">
                Burned-in pixel text is not automatically removed. Review before external sharing.
              </div>
              {data.representative && typeof data.representative === "object" ? (
                <div className="space-y-1 rounded-lg border border-white/10 bg-white/[0.02] p-2">
                  {Object.entries(data.representative as Record<string, unknown>).map(([key, value]) => (
                    <div key={key} className="flex justify-between gap-3">
                      <span className="text-slate-600">{key}</span>
                      <span className="max-w-[65%] break-all text-right text-slate-300">{String(value)}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </>
          ) : null}
        </div>
      )}
    </section>
  );
}
