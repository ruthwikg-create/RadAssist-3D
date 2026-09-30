"use client";

import { useEffect } from "react";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="grid min-h-screen place-items-center bg-[#071014] px-6 text-white">
      <div className="max-w-lg rounded-2xl border border-rose-300/10 bg-white/[0.03] p-6 text-center">
        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-rose-200">Workspace error</div>
        <h1 className="mt-2 text-xl font-semibold">The imaging workspace could not be rendered.</h1>
        <p className="mt-3 text-sm leading-6 text-slate-400">Reload the workspace. Uploaded files remain on the backend only if a completed case was already saved.</p>
        <button type="button" onClick={() => reset()} className="mt-5 rounded-xl bg-teal-300 px-4 py-2.5 text-sm font-bold text-slate-950 hover:bg-teal-200">Try again</button>
      </div>
    </main>
  );
}
