"use client";

import { AlertTriangle, FileSearch, Loader2 } from "lucide-react";
import type { Cell, ResultItem, Source } from "@/lib/types";

interface Props {
  /** Files to show, in upload order; ones without a result yet render as pending rows. */
  names: string[];
  results: Map<string, ResultItem>;
  columns: string[];
  busy: boolean;
}

/** The user's columns, or every column some document filled in (the invoice defaults are mostly empty). */
export function tableColumns(results: ResultItem[], requested: string[]): string[] {
  if (requested.length) return requested;
  const all = [...new Set(results.flatMap((r) => r.fields?.columns ?? []))];
  return all.filter((c) => results.some((r) => r.fields?.rows.some((row) => row[c]?.value != null)));
}

export function formatSource(s: Source) {
  return `p${s.page} L${s.line}: ${s.text}`;
}

function csvEscape(v: string) {
  return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
}

/** One CSV row per extracted row across all files, each value followed by its source. */
export function toCsv(results: ResultItem[], columns: string[]) {
  const header = ["File", ...columns.flatMap((c) => [c, `${c} (source)`]), "Error"];
  const lines = [header];
  for (const r of results) {
    if (r.error) {
      lines.push([r.filename, ...columns.flatMap(() => ["", ""]), r.error]);
      continue;
    }
    for (const row of r.fields?.rows ?? []) {
      const cells = columns.flatMap((c) => {
        const cell = row[c];
        return [cell?.value ?? "", cell?.source ? formatSource(cell.source) : ""];
      });
      lines.push([r.filename, ...cells, ""]);
    }
  }
  return lines.map((l) => l.map(csvEscape).join(",")).join("\n");
}

function ValueCell({ cell }: { cell: Cell | undefined }) {
  if (cell?.value == null) return <span className="text-white/25">—</span>;
  const s = cell.source;
  const tooltip = s
    ? `Page ${s.page}, line ${s.line}${s.confidence != null ? ` · ${Math.round(s.confidence * 100)}% OCR confidence` : ""}\n“${s.text}”`
    : "The value wasn't found word for word in the document text";
  return (
    <div title={tooltip} className="space-y-1">
      <p className="font-medium text-white">{cell.value}</p>
      {s ? (
        <p className="flex min-w-0 items-center gap-1.5 text-[11px] text-white/40">
          <span className="shrink-0 rounded bg-cyan-400/10 px-1.5 py-0.5 font-mono text-cyan-200/80">
            p{s.page} · L{s.line}
          </span>
          <span className="truncate italic">“{s.text}”</span>
        </p>
      ) : (
        <p className="text-[11px] text-amber-200/60">source not located</p>
      )}
    </div>
  );
}

export default function FieldsTable({ names, results, columns, busy }: Props) {
  const anyRows = names.some((n) => results.get(n)?.fields?.rows.length);

  if (!columns.length && !busy) {
    return (
      <div className="flex min-h-[240px] flex-col items-center justify-center text-center text-sm text-white/45">
        <FileSearch className="mb-3 h-8 w-8 text-white/25" />
        {anyRows || names.some((n) => results.get(n)?.error) ? "No values were found in these documents." : "Nothing extracted yet."}
      </div>
    );
  }

  return (
    <div className="scroll-thin overflow-x-auto rounded-2xl border border-white/10">
      <table className="w-full text-left text-sm">
        <thead className="bg-white/[0.04] text-xs uppercase tracking-wider text-white/45">
          <tr>
            <th className="sticky left-0 z-10 bg-ink-900 px-4 py-3 font-semibold">File</th>
            {columns.map((c) => (
              <th key={c} className="min-w-[180px] px-4 py-3 font-semibold">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {names.map((name) => {
            const r = results.get(name);
            const fileCell = (rowSpan = 1) => (
              <td rowSpan={rowSpan} className="sticky left-0 z-10 max-w-[200px] bg-ink-900 px-4 py-3 align-top">
                <p className="truncate font-mono text-xs text-violet-200" title={name}>{name}</p>
              </td>
            );

            if (!r) {
              return (
                <tr key={name}>
                  {fileCell()}
                  <td colSpan={Math.max(columns.length, 1)} className="px-4 py-3">
                    {busy ? (
                      <span className="flex items-center gap-2 text-xs text-white/45">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Processing…
                        <span className="h-2 flex-1 rounded bg-white/[0.05] shimmer-bg animate-shimmer" />
                      </span>
                    ) : (
                      <span className="text-xs text-white/35">No result</span>
                    )}
                  </td>
                </tr>
              );
            }

            if (r.error || !r.fields?.rows.length) {
              return (
                <tr key={name}>
                  {fileCell()}
                  <td colSpan={Math.max(columns.length, 1)} className="px-4 py-3 text-xs">
                    {r.error ? (
                      <span className="flex items-center gap-1.5 text-rose-300">
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> {r.error}
                      </span>
                    ) : (
                      <span className="text-white/35 italic">No matching values in this document</span>
                    )}
                  </td>
                </tr>
              );
            }

            return r.fields.rows.map((row, i) => (
              <tr key={`${name}-${i}`} className="transition-colors hover:bg-violet-500/[0.06]">
                {i === 0 && fileCell(r.fields!.rows.length)}
                {columns.map((c) => (
                  <td key={c} className="max-w-[320px] px-4 py-3 align-top">
                    <ValueCell cell={row[c]} />
                  </td>
                ))}
              </tr>
            ));
          })}
        </tbody>
      </table>
    </div>
  );
}
