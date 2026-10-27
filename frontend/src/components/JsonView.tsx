import type { ReactNode } from "react";

const INDENT = "  ";

function render(value: unknown, depth: number): ReactNode {
  const pad = INDENT.repeat(depth + 1);
  const close = INDENT.repeat(depth);

  if (value === null) return <span className="json-null">null</span>;
  if (typeof value === "string") return <span className="json-str">{JSON.stringify(value)}</span>;
  if (typeof value === "number") return <span className="json-num">{value}</span>;
  if (typeof value === "boolean") return <span className="json-bool">{String(value)}</span>;

  if (Array.isArray(value)) {
    if (!value.length) return "[]";
    return (
      <>
        {"[\n"}
        {value.map((v, i) => (
          <span key={i}>
            {pad}
            {render(v, depth + 1)}
            {i < value.length - 1 ? ",\n" : "\n"}
          </span>
        ))}
        {close}]
      </>
    );
  }

  const entries = Object.entries(value as Record<string, unknown>);
  if (!entries.length) return "{}";
  return (
    <>
      {"{\n"}
      {entries.map(([k, v], i) => (
        <span key={k}>
          {pad}
          <span className="json-key">{JSON.stringify(k)}</span>: {render(v, depth + 1)}
          {i < entries.length - 1 ? ",\n" : "\n"}
        </span>
      ))}
      {close}
      {"}"}
    </>
  );
}

export default function JsonView({ data }: { data: unknown }) {
  return (
    <pre className="scroll-thin overflow-auto rounded-2xl border border-white/10 bg-ink-900/80 p-5 font-mono text-[13px] leading-relaxed text-white/70">
      {render(data, 0)}
    </pre>
  );
}
