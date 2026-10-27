"use client";

import { useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FileText, Loader2, UploadCloud, X, Zap } from "lucide-react";
import Pipeline from "./Pipeline";
import type { Failure, Stage } from "@/lib/types";

interface Props {
  files: File[];
  stage: Stage;
  failure: Failure | null;
  onAdd: (files: File[]) => void;
  onRemove: (index: number) => void;
  onProcess: () => void;
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function UploadPanel({ files, stage, failure, onAdd, onRemove, onProcess }: Props) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const busy = stage === "upload" || stage === "ocr" || stage === "ai";

  const accept = (list: FileList | null) => {
    if (!list) return;
    const pdfs = Array.from(list).filter((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length) onAdd(pdfs);
  };

  return (
    <section className="glass flex flex-col p-6">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-lg font-semibold tracking-tight">Documents</h2>
        <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-white/60">
          {files.length} {files.length === 1 ? "file" : "files"}
        </span>
      </div>

      <motion.button
        type="button"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!busy) accept(e.dataTransfer.files);
        }}
        animate={{ scale: dragging ? 1.02 : 1 }}
        className={`group relative flex flex-col items-center justify-center overflow-hidden rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
          dragging ? "border-cyan-300 bg-cyan-400/10" : "border-white/15 bg-white/[0.02] hover:border-violet-400/60 hover:bg-violet-500/[0.06]"
        }`}
      >
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_50%_0%,rgba(167,139,250,0.18),transparent_60%)] opacity-0 transition-opacity group-hover:opacity-100" />
        <motion.div
          animate={{ y: dragging ? -6 : 0 }}
          className="mb-4 grid h-16 w-16 place-items-center rounded-2xl bg-gradient-to-br from-violet-500 to-cyan-500 shadow-xl shadow-violet-500/30"
        >
          <UploadCloud className="h-8 w-8 text-white" />
        </motion.div>
        <p className="font-semibold">{dragging ? "Release to add" : "Drag & drop PDFs here"}</p>
        <p className="mt-1 text-sm text-white/50">
          or <span className="font-medium text-cyan-300 underline-offset-4 group-hover:underline">browse files</span> · multiple allowed
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,application/pdf"
          className="hidden"
          onChange={(e) => {
            accept(e.target.files);
            e.target.value = "";
          }}
        />
      </motion.button>

      <ul className="scroll-thin mt-4 max-h-56 space-y-2 overflow-y-auto pr-1">
        <AnimatePresence initial={false}>
          {files.map((file, i) => (
            <motion.li
              key={`${file.name}-${file.size}-${file.lastModified}`}
              layout
              initial={{ opacity: 0, x: -16 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 16, height: 0, marginTop: 0 }}
              className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5"
            >
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-rose-500/15 text-rose-300">
                <FileText className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{file.name}</p>
                <p className="text-xs text-white/40">{formatSize(file.size)}</p>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={() => onRemove(i)}
                aria-label={`Remove ${file.name}`}
                className="grid h-8 w-8 place-items-center rounded-lg text-white/40 transition hover:bg-rose-500/15 hover:text-rose-300 disabled:opacity-40"
              >
                <X className="h-4 w-4" />
              </button>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>

      <motion.button
        type="button"
        whileHover={{ scale: files.length && !busy ? 1.02 : 1 }}
        whileTap={{ scale: 0.98 }}
        disabled={!files.length || busy}
        onClick={onProcess}
        className="relative mt-5 flex h-13 items-center justify-center gap-2 overflow-hidden rounded-xl bg-gradient-to-r from-violet-600 via-fuchsia-500 to-cyan-500 py-3.5 font-semibold text-white shadow-xl shadow-fuchsia-500/25 transition disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
      >
        <span className="absolute inset-0 shimmer-bg animate-shimmer" />
        {busy ? <Loader2 className="relative h-5 w-5 animate-spin" /> : <Zap className="relative h-5 w-5" fill="currentColor" />}
        <span className="relative">{busy ? "Extracting…" : "Extract data"}</span>
      </motion.button>

      <AnimatePresence>
        {stage !== "idle" && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
            <Pipeline stage={stage} failure={failure} />
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
