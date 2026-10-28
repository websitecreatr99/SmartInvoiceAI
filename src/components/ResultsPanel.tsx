"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Check, Copy, Download, FileJson, LayoutGrid, Loader2, Table2 } from "lucide-react";
import DocumentView from "./DocumentView";
import FieldsTable, { tableColumns, toCsv } from "./FieldsTable";
import JsonView from "./JsonView";
import { parseExtraction } from "@/lib/api";
import type { ResultItem, Stage } from "@/lib/types";

type View = "table" | "visual" | "json";

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
      <p className="mt-1 max-w-xs text-sm text-white/50">Add documents on the left and hit <b className="text-white/80">Extract data</b>. Results will appear here.</p>
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

type Selection = "all" | string;

function FileStatus({ result, busy }: { result: ResultItem | undefined; busy: boolean }) {
  if (!result) return busy ? <Loader2 className="h-3 w-3 animate-spin text-white/45" /> : null;
  if (result.error) return <AlertTriangle className="h-3 w-3 text-rose-300" />;
  return <Check className="h-3 w-3 text-emerald-300" strokeWidth={3} />;
}

interface Props {
  results: ResultItem[];
  /** Every file in the job, in upload order, including ones still processing. */
  files: string[];
  /** Columns the user asked for; empty means the default invoice fields. */
  columns: string[];
  stage: Stage;
  error: string | null;
}

export default function ResultsPanel({ results, files, columns, stage, error }: Props) {
  const [view, setView] = useState<View>("table");
  const [active, setActive] = useState<Selection>("all");
  const [copied, setCopied] = useState(false);

  const busy = stage === "upload" || stage === "ocr" || stage === "ai";
  const byName = new Map(results.map((r) => [r.filename, r]));
  const names = files.length ? files : results.map((r) => r.filename);
  const selected = active === "all" || !names.includes(active) ? names : [active];
  const selectedResults = selected.map((n) => byName.get(n)).filter((r): r is ResultItem => !!r);
  const tableCols = tableColumns(selectedResults, columns);

  // The visual layout is for the invoice schema; with custom columns the table is the visual.
  const hasVisual = results.some((r) => parseExtraction(r));
  const views: View[] = hasVisual ? ["table", "visual", "json"] : ["table", "json"];
  const shownView = views.includes(view) ? view : "table";

  const jsonPayload = () => {
    const items = selectedResults.map((r) => ({ ...r, structured_data: parseExtraction(r) ?? r.structured_data }));
    return active === "all" ? items : items[0];
  };
  const exportText = () => (shownView === "table" ? toCsv(selectedResults, tableCols) : JSON.stringify(jsonPayload(), null, 2));

  const copy = async () => {
    await navigator.clipboard.writeText(exportText());
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const download = () => {
    const csv = shownView === "table";
    const blob = new Blob([exportText()], { type: csv ? "text/csv" : "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${active === "all" ? "extraction" : active}.${csv ? "csv" : "json"}`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const done = names.filter((n) => byName.has(n)).length;

  return (
    <section className="glass flex min-h-[600px] flex-col p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Extracted results</h2>
          {names.length > 0 && (
            <p className="text-xs text-white/45">
              {done}/{names.length} files {busy ? "done · results appear as each file finishes" : "processed"}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {selectedResults.length > 0 && (
            <>
              <button onClick={copy} className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-white/70 transition hover:bg-white/10 hover:text-white">
                {copied ? <Check className="h-3.5 w-3.5 text-emerald-300" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? "Copied" : "Copy"}
              </button>
              <button onClick={download} className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-white/70 transition hover:bg-white/10 hover:text-white">
                <Download className="h-3.5 w-3.5" /> {shownView === "table" ? "CSV" : "JSON"}
              </button>
            </>
          )}
          <div className="relative flex rounded-xl border border-white/10 bg-white/5 p-1">
            {views.map((v) => {
              const Icon = v === "table" ? Table2 : v === "visual" ? LayoutGrid : FileJson;
              return (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className={`relative z-10 flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${shownView === v ? "text-white" : "text-white/50 hover:text-white/80"}`}
                >
                  {shownView === v && (
                    <motion.span layoutId="view-pill" className="absolute inset-0 -z-10 rounded-lg bg-gradient-to-r from-violet-500/80 to-cyan-500/80" />
                  )}
                  <Icon className="h-3.5 w-3.5" />
                  {v === "table" ? "Table" : v === "visual" ? "Visual" : "JSON"}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {names.length > 1 && (
        <div className="scroll-thin mb-5 flex gap-2 overflow-x-auto pb-1">
          {(["all", ...names] as Selection[]).map((n) => (
            <button
              key={n}
              onClick={() => setActive(n)}
              className={`flex shrink-0 items-center gap-1.5 rounded-full border px-4 py-1.5 text-xs font-medium transition ${
                n === active || (n === "all" && !names.includes(active))
                  ? "border-violet-400/60 bg-violet-500/20 text-white"
                  : "border-white/10 bg-white/[0.03] text-white/55 hover:text-white"
              }`}
            >
              {n === "all" ? `All files (${names.length})` : (
                <>
                  <FileStatus result={byName.get(n)} busy={busy} /> {n}
                </>
              )}
            </button>
          ))}
        </div>
      )}

      {error && names.length > 0 && (
        <p className="mb-4 flex items-center gap-2 rounded-xl border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-200">
          <AlertTriangle className="h-4 w-4 shrink-0" /> {error}
        </p>
      )}

      <div className="flex-1">
        <AnimatePresence mode="wait">
          <motion.div
            key={!names.length ? (busy ? "loading" : error ? "error" : "empty") : `${active}-${shownView}`}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.25 }}
            className="h-full"
          >
            {!names.length ? (
              busy ? (
                <LoadingState />
              ) : error ? (
                <div className="flex min-h-[420px] flex-col items-center justify-center text-center">
                  <span className="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-rose-500/15 text-rose-300"><AlertTriangle className="h-7 w-7" /></span>
                  <h3 className="font-semibold">Extraction failed</h3>
                  <p className="mt-1 max-w-md text-sm text-white/50">{error}</p>
                </div>
              ) : (
                <EmptyState />
              )
            ) : shownView === "table" ? (
              <FieldsTable names={selected} results={byName} columns={tableCols} busy={busy} />
            ) : shownView === "json" ? (
              selectedResults.length ? <JsonView data={jsonPayload()} /> : <LoadingState />
            ) : (
              <div className="space-y-10">
                {selected.map((name) => {
                  const r = byName.get(name);
                  const parsed = r ? parseExtraction(r) : null;
                  return (
                    <div key={name} className="space-y-4">
                      {selected.length > 1 && (
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-sm font-semibold text-violet-300">{name}</span>
                          <span className="h-px flex-1 bg-gradient-to-r from-violet-400/40 to-transparent" />
                        </div>
                      )}
                      {!r ? (
                        busy ? <div className="h-32 rounded-2xl bg-white/[0.04] shimmer-bg animate-shimmer" /> : <p className="text-sm text-white/35">No result</p>
                      ) : r.error ? (
                        <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 p-4 text-sm text-rose-200">{r.error}</p>
                      ) : parsed ? (
                        <DocumentView data={parsed} />
                      ) : (
                        <JsonView data={r} />
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </section>
  );
}
