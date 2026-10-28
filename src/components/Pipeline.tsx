"use client";

import { motion } from "framer-motion";
import { AlertTriangle, Check, CloudUpload, ScanText, Sparkles, Braces, X } from "lucide-react";
import type { Failure, Progress, Stage, StepKey } from "@/lib/types";

const STEPS = [
  { key: "upload", label: "Upload", hint: "Sending files to the server", icon: CloudUpload },
  { key: "ocr", label: "OCR", hint: "Reading text from every page", icon: ScanText },
  { key: "ai", label: "AI extraction", hint: "Parsing headers & line items", icon: Sparkles },
  { key: "done", label: "Structured", hint: "Validated JSON ready", icon: Braces },
] as const;

const ORDER: StepKey[] = ["upload", "ocr", "ai", "done"];

type StepStatus = "done" | "active" | "pending" | "failed" | "partial" | "skipped";

function statusOf(i: number, stage: Stage, failure: Failure | null): StepStatus {
  if (failure) {
    const failedAt = ORDER.indexOf(failure.step);
    const partial = failure.failed < failure.total;
    if (i < failedAt) return "done";
    if (i === failedAt) return partial ? "partial" : "failed";
    // Documents that got past the failing step still finished.
    return partial ? "done" : "skipped";
  }
  const current = ORDER.indexOf(stage as StepKey);
  if (stage === "done" || current > i) return "done";
  if (current === i) return "active";
  return "pending";
}

const BADGE: Record<StepStatus, string> = {
  done: "border-transparent bg-gradient-to-br from-violet-500 to-cyan-500 text-white shadow-lg shadow-violet-500/30",
  active: "border-violet-400/60 bg-violet-500/15 text-violet-200",
  pending: "border-white/10 bg-white/[0.03] text-white/35",
  skipped: "border-white/10 bg-white/[0.03] text-white/25",
  failed: "border-transparent bg-rose-500 text-white shadow-lg shadow-rose-500/30",
  partial: "border-transparent bg-amber-400 text-ink-950 shadow-lg shadow-amber-400/30",
};

export default function Pipeline({ stage, failure, progress }: { stage: Stage; failure: Failure | null; progress: Progress | null }) {
  return (
    <ol className="relative mt-6 space-y-1">
      {STEPS.map((step, i) => {
        const status = statusOf(i, stage, failure);
        const isFailure = status === "failed" || status === "partial";
        const Icon = step.icon;
        const hint = isFailure
          ? status === "partial"
            ? `${failure!.failed} of ${failure!.total} failed: ${failure!.message}`
            : failure!.message
          : status === "skipped"
            ? "Skipped"
            : status === "active" && step.key !== "upload" && progress?.total
              ? `${progress.done} of ${progress.total} files done`
              : step.hint;

        return (
          <li
            key={step.key}
            data-step={step.key}
            data-status={status}
            className={`relative flex items-center gap-4 rounded-xl px-2 py-2 ${
              status === "failed" ? "bg-rose-500/[0.07]" : status === "partial" ? "bg-amber-400/[0.07]" : ""
            }`}
          >
            {i < STEPS.length - 1 && (
              <span className="absolute left-[1.55rem] top-11 h-5 w-px bg-white/10">
                <motion.span
                  className="absolute inset-x-0 top-0 bg-gradient-to-b from-violet-400 to-cyan-400"
                  initial={false}
                  animate={{ height: status === "done" ? "100%" : "0%" }}
                  transition={{ duration: 0.5 }}
                />
              </span>
            )}
            <span
              className={`relative grid h-9 w-9 shrink-0 place-items-center rounded-xl border transition-colors duration-500 ${BADGE[status]}`}
            >
              {status === "active" && <span className="absolute inset-0 animate-ping rounded-xl border border-violet-400/50" />}
              {status === "done" ? (
                <Check className="h-4 w-4" strokeWidth={3} />
              ) : status === "failed" ? (
                <X className="h-4 w-4" strokeWidth={3} />
              ) : status === "partial" ? (
                <AlertTriangle className="h-4 w-4" strokeWidth={2.5} />
              ) : (
                <Icon className="h-4 w-4" />
              )}
            </span>
            <div className="min-w-0">
              <p
                className={`text-sm font-semibold ${
                  status === "failed"
                    ? "text-rose-200"
                    : status === "partial"
                      ? "text-amber-200"
                      : status === "done" || status === "active"
                        ? "text-white"
                        : "text-white/40"
                }`}
              >
                {step.label}
              </p>
              <p
                title={isFailure ? failure!.message : undefined}
                className={`truncate text-xs ${
                  status === "failed" ? "text-rose-300/80" : status === "partial" ? "text-amber-200/80" : "text-white/40"
                }`}
              >
                {hint}
              </p>
            </div>
            {status === "active" && (
              <span className="ml-auto h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-white/10">
                <span className="block h-full w-full rounded-full bg-gradient-to-r from-violet-400 via-cyan-300 to-violet-400 shimmer-bg animate-shimmer" />
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
