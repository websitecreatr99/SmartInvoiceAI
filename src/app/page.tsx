"use client";

import { useRef, useState } from "react";
import { motion } from "framer-motion";
import { FileText, Quote, ScanText, Sparkles } from "lucide-react";
import Background from "@/components/Background";
import UploadPanel from "@/components/UploadPanel";
import ResultsPanel from "@/components/ResultsPanel";
import { createJob, getJob, parseExtraction } from "@/lib/api";
import type { Failure, Progress, ResultItem, Stage, StepKey } from "@/lib/types";

// Workers run OCR and LLM extraction back to back, so the OCR → AI hand-off
// in the stepper is estimated rather than reported by the backend.
const OCR_ESTIMATE_MS = 8000;
const POLL_MS = 1500;
const POLL_TIMEOUT_MS = 15 * 60 * 1000;
// Ride out brief network or proxy hiccups while polling.
const MAX_POLL_ERRORS = 3;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Per-document errors only carry a message, so infer which step produced it. */
function stepForError(message: string): StepKey {
  return /LLM|Gemini|Validation Error|extraction returned/i.test(message) ? "ai" : "ocr";
}

/** Summarise per-document failures in a successful response, or null if every document worked. */
function documentFailure(results: ResultItem[]): Failure | null {
  const failed = results.filter((r) => r.error || (!r.fields && !parseExtraction(r)));
  if (!failed.length) return null;
  const message = failed[0].error ?? "Unreadable extraction output";
  return { step: stepForError(message), message, failed: failed.length, total: results.length };
}

export default function Home() {
  const [files, setFiles] = useState<File[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [stage, setStage] = useState<Stage>("idle");
  const [results, setResults] = useState<ResultItem[]>([]);
  // Names the server gave each file (deduplicated), in upload order, and the columns the job ran with.
  const [jobFiles, setJobFiles] = useState<string[]>([]);
  const [jobColumns, setJobColumns] = useState<string[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const currentStep = useRef<StepKey>("upload");

  const goTo = (step: StepKey) => {
    currentStep.current = step;
    setStage(step);
  };

  const addFiles = (incoming: File[]) =>
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      return [...prev, ...incoming.filter((f) => !seen.has(`${f.name}:${f.size}`))];
    });

  /** Poll the job, appending each file's result as soon as its worker finishes. */
  const waitForJob = async (jobId: string) => {
    const deadline = Date.now() + POLL_TIMEOUT_MS;
    let errors = 0;
    while (Date.now() < deadline) {
      try {
        const job = await getJob(jobId);
        errors = 0;
        setResults(job.results);
        setProgress(job.progress);
        if (job.status === "done") return job.results;
      } catch (e) {
        if (++errors >= MAX_POLL_ERRORS) throw e;
      }
      await sleep(POLL_MS);
    }
    throw new Error(`Still processing after ${POLL_TIMEOUT_MS / 60000} minutes (job ${jobId})`);
  };

  const run = async () => {
    setError(null);
    setFailure(null);
    setResults([]);
    setProgress(null);
    try {
      goTo("upload");
      const job = await createJob(files, columns);
      setJobFiles(job.files);
      setJobColumns(columns);
      setProgress({ done: 0, total: job.files.length });
      goTo("ocr");
      timer.current = setTimeout(() => goTo("ai"), OCR_ESTIMATE_MS);
      const res = await waitForJob(job.job_id);
      clearTimeout(timer.current);
      setFailure(documentFailure(res));
      setStage("done");
    } catch (e) {
      clearTimeout(timer.current);
      const message = e instanceof Error ? e.message : "Something went wrong";
      setError(message);
      setFailure({ step: currentStep.current, message, failed: files.length, total: files.length });
      setStage("error");
    }
  };

  return (
    <>
      <Background />

      <header className="mx-auto flex max-w-7xl items-center justify-between px-4 py-6 sm:px-8">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-violet-500 via-fuchsia-500 to-cyan-400 shadow-lg shadow-violet-500/40">
            <FileText className="h-5 w-5 text-white" />
          </span>
          <span className="text-xl font-bold tracking-tight">
            Invoice<span className="grad-text">AI</span>
          </span>
        </div>
        <span className="hidden items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 text-xs font-medium text-emerald-200 sm:flex">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
          OCR + LLM pipeline
        </span>
      </header>

      <main className="mx-auto max-w-7xl px-4 pb-20 sm:px-8">
        <section className="mx-auto max-w-3xl pt-8 pb-14 text-center">
          <motion.span
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="inline-flex items-center gap-2 rounded-full border border-violet-400/30 bg-violet-500/10 px-4 py-1.5 text-xs font-semibold tracking-wide text-violet-200"
          >
            <Sparkles className="h-3.5 w-3.5" /> PDFs, scans & docs → clean data
          </motion.span>
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1, duration: 0.6 }}
            className="mt-6 text-4xl font-extrabold leading-[1.08] tracking-tight sm:text-6xl"
          >
            Turn messy invoices into <span className="grad-text">structured data</span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.6 }}
            className="mt-5 text-base text-white/55 sm:text-lg"
          >
            Drop purchase orders, invoices or any document, as many as you like. Each file is processed in parallel, and
            every value comes back with the exact line it was read from.
          </motion.p>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.35 }}
            className="mt-8 flex flex-wrap justify-center gap-3 text-xs text-white/50"
          >
            {[
              { icon: ScanText, label: "PaddleOCR text recognition" },
              { icon: Sparkles, label: "LLM field extraction" },
              { icon: FileText, label: "Pydantic-validated schema" },
              { icon: Quote, label: "Source line for every value" },
            ].map(({ icon: Icon, label }) => (
              <span key={label} className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5">
                <Icon className="h-3.5 w-3.5 text-cyan-300" /> {label}
              </span>
            ))}
          </motion.div>
        </section>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.7 }}
          className="grid items-start gap-6 lg:grid-cols-[380px_1fr]"
        >
          <div className="lg:sticky lg:top-6">
            <UploadPanel
              files={files}
              columns={columns}
              stage={stage}
              failure={failure}
              progress={progress}
              onAdd={addFiles}
              onColumnsChange={setColumns}
              onRemove={(i) => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
              onProcess={run}
            />
          </div>
          <ResultsPanel results={results} files={jobFiles} columns={jobColumns} stage={stage} error={error} />
        </motion.div>
      </main>
    </>
  );
}
