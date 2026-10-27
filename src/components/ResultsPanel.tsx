"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Check, Copy, Download, FileJson, LayoutGrid } from "lucide-react";
import DocumentView from "./DocumentView";
import JsonView from "./JsonView";
import { parseExtraction } from "@/lib/api";
import type { ResultItem, Stage } from "@/lib/types";

type View = "visual" | "json";

function EmptyState() {
  return (
    <div className="flex h-full min-h-[420px] flex-col items-center justify-center text-center">
      <div className="relative mb-8 h-36 w-32">
        {[0, 1, 2].map((i) => (
          <motion.div
            key={i}
            className="absolute inset-0 rounded-2xl border border-white/15 bg-gradient-to-br from-white/10 to-white/[0.02] p-4 backdrop-blur"
            initial={{ rotate: 0 }}
            animate={{ rotate: (i - 1) * 9, x: (i - 1) * 18, y: [0, -6, 0] }}
            transition={{ y: { repeat: Infinity, duration: 3, delay: i * 0.3 }, default: { duration: 0.8 } }}
            style={{ zIndex: i === 1 ? 3 : 1 }}
          >
            {i === 1 && (
              <div className="space-y-2">
                <div className="h-2 w-2/3 rounded bg-violet-400/60" />
                <div className="h-1.5 w-full rounded bg-white/20" />
                <div className="h-1.5 w-5/6 rounded bg-white/20" />
                <div className="h-1.5 w-1/2 rounded bg-cyan-300/50" />
                <div className="h-1.5 w-3/4 rounded bg-white/20" />
              </div>
            )}
          </motion.div>
        ))}
      </div>
      <h3 className="text-lg font-semibold">Nothing extracted yet</h3>
      <p className="mt-1 max-w-xs text-sm text-white/50">Add PDFs on the left and hit <b className="text-white/80">Extract data</b>. Results will appear here.</p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        {[0, 1, 2].map((i) => <div key={i} className="h-24 rounded-2xl bg-white/[0.04] shimmer-bg animate-shimmer" />)}
      </div>
      <div className="grid grid-cols-3 gap-3">
        {Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-16 rounded-xl bg-white/[0.04] shimmer-bg animate-shimmer" />)}
      </div>
      <div className="h-64 rounded-2xl bg-white/[0.04] shimmer-bg animate-shimmer" />
    </div>
  );
}

export default function ResultsPanel({ results, stage, error }: { results: ResultItem[]; stage: Stage; error: string | null }) {
  const [view, setView] = useState<View>("visual");
  const [active, setActive] = useState(0);
  const [copied, setCopied] = useState(false);

  const busy = stage === "upload" || stage === "ocr" || stage === "ai";
  const current = results[Math.min(active, results.length - 1)];
  const parsed = current ? parseExtraction(current) : null;
  const payload = parsed ?? current?.structured_data;

  const copy = async () => {
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const download = () => {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = current.filename.endsWith(".json") ? current.filename : `${current.filename}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <section className="glass flex min-h-[600px] flex-col p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold tracking-tight">Extracted results</h2>
        <div className="flex items-center gap-2">
          {current && !busy && (
            <>
              <button onClick={copy} className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-white/70 transition hover:bg-white/10 hover:text-white">
                {copied ? <Check className="h-3.5 w-3.5 text-emerald-300" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? "Copied" : "Copy"}
              </button>
              <button onClick={download} className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-white/70 transition hover:bg-white/10 hover:text-white">
                <Download className="h-3.5 w-3.5" /> Download
              </button>
            </>
          )}
          <div className="relative flex rounded-xl border border-white/10 bg-white/5 p-1">
            {(["visual", "json"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`relative z-10 flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${view === v ? "text-white" : "text-white/50 hover:text-white/80"}`}
              >
                {view === v && (
                  <motion.span layoutId="view-pill" className="absolute inset-0 -z-10 rounded-lg bg-gradient-to-r from-violet-500/80 to-cyan-500/80" />
                )}
                {v === "visual" ? <LayoutGrid className="h-3.5 w-3.5" /> : <FileJson className="h-3.5 w-3.5" />}
                {v === "visual" ? "Visual" : "JSON"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {results.length > 1 && !busy && (
        <div className="scroll-thin mb-5 flex gap-2 overflow-x-auto pb-1">
          {results.map((r, i) => (
            <button
              key={r.filename}
              onClick={() => setActive(i)}
              className={`shrink-0 rounded-full border px-4 py-1.5 text-xs font-medium transition ${
                i === active ? "border-violet-400/60 bg-violet-500/20 text-white" : "border-white/10 bg-white/[0.03] text-white/55 hover:text-white"
              }`}
            >
              {r.filename.replace(/\.json$/, "")}
            </button>
          ))}
        </div>
      )}

      <div className="flex-1">
        <AnimatePresence mode="wait">
          <motion.div
            key={busy ? "loading" : error ? "error" : current ? `${active}-${view}` : "empty"}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.25 }}
            className="h-full"
          >
            {busy ? (
              <LoadingState />
            ) : error ? (
              <div className="flex min-h-[420px] flex-col items-center justify-center text-center">
                <span className="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-rose-500/15 text-rose-300"><AlertTriangle className="h-7 w-7" /></span>
                <h3 className="font-semibold">Extraction failed</h3>
                <p className="mt-1 max-w-md text-sm text-white/50">{error}</p>
              </div>
            ) : !current ? (
              <EmptyState />
            ) : current.error ? (
              <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 p-4 text-sm text-rose-200">{current.error}</p>
            ) : view === "json" || !parsed ? (
              <JsonView data={payload} />
            ) : (
              <DocumentView data={parsed} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </section>
  );
}
