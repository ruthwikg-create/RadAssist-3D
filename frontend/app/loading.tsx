export default function Loading() {
  return (
    <main className="grid min-h-screen place-items-center bg-[#071014] text-slate-300">
      <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-4 text-sm">
        <div className="size-4 animate-spin rounded-full border-2 border-teal-200/20 border-t-teal-200" />
        Loading RadAssist 3D…
      </div>
    </main>
  );
}
