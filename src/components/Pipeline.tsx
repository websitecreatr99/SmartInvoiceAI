"use client";

import { motion } from "framer-motion";
import { Check, CloudUpload, ScanText, Sparkles, Braces } from "lucide-react";
import type { Stage } from "@/lib/types";

const STEPS = [
  { key: "upload", label: "Upload", hint: "Sending files to the server", icon: CloudUpload },
  { key: "ocr", label: "OCR", hint: "Reading text from every page", icon: ScanText },
  { key: "ai", label: "AI extraction", hint: "Parsing headers & line items", icon: Sparkles },
  { key: "done", label: "Structured", hint: "Validated JSON ready", icon: Braces },
] as const;

const ORDER: Stage[] = ["upload", "ocr", "ai", "done"];

export default function Pipeline({ stage }: { stage: Stage }) {
  const current = ORDER.indexOf(stage);

  return (
    <ol className="relative mt-6 space-y-1">
      {STEPS.map((step, i) => {
        const done = current > i || stage === "done";
        const active = current === i && stage !== "done";
        const Icon = step.icon;
        return (
          <li key={step.key} className="relative flex items-center gap-4 rounded-xl px-2 py-2">
            {i < STEPS.length - 1 && (
              <span className="absolute left-[1.55rem] top-11 h-5 w-px bg-white/10">
                <motion.span
                  className="absolute inset-x-0 top-0 bg-gradient-to-b from-violet-400 to-cyan-400"
                  initial={false}
                  animate={{ height: done ? "100%" : "0%" }}
                  transition={{ duration: 0.5 }}
                />
              </span>
            )}
            <span
              className={`relative grid h-9 w-9 shrink-0 place-items-center rounded-xl border transition-colors duration-500 ${
                done
                  ? "border-transparent bg-gradient-to-br from-violet-500 to-cyan-500 text-white shadow-lg shadow-violet-500/30"
                  : active
                    ? "border-violet-400/60 bg-violet-500/15 text-violet-200"
                    : "border-white/10 bg-white/[0.03] text-white/35"
              }`}
            >
              {active && <span className="absolute inset-0 animate-ping rounded-xl border border-violet-400/50" />}
              {done ? <Check className="h-4 w-4" strokeWidth={3} /> : <Icon className="h-4 w-4" />}
            </span>
            <div className="min-w-0">
              <p className={`text-sm font-semibold ${done || active ? "text-white" : "text-white/40"}`}>{step.label}</p>
              <p className="truncate text-xs text-white/40">{step.hint}</p>
            </div>
            {active && (
              <span className="ml-auto h-1.5 w-16 overflow-hidden rounded-full bg-white/10">
                <span className="block h-full w-full rounded-full bg-gradient-to-r from-violet-400 via-cyan-300 to-violet-400 shimmer-bg animate-shimmer" />
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
