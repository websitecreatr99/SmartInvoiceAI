"use client";

import { useState } from "react";
import { ExternalLink, Eye, EyeOff, Info, KeyRound } from "lucide-react";

interface Props {
  apiKey: string;
  remember: boolean;
  disabled: boolean;
  /** The API answers keyless jobs with sample data (GET /config). */
  demoWithoutKey: boolean;
  onChange: (key: string) => void;
  onRememberChange: (remember: boolean) => void;
}

/** Optional Gemini API key. Sent only with the user's own jobs; without it the results are sample data. */
export default function ApiKeyInput({ apiKey, remember, disabled, demoWithoutKey, onChange, onRememberChange }: Props) {
  const [visible, setVisible] = useState(false);
  const hasKey = apiKey.trim().length > 0;

  return (
    <div className="mt-5">
      <label htmlFor="api-key" className="mb-2 flex items-center gap-1.5 text-sm font-medium">
        <KeyRound className="h-4 w-4 text-cyan-300" /> Gemini API key
        <span className="text-xs font-normal text-white/40">optional</span>
        <a
          href="https://aistudio.google.com/apikey"
          target="_blank"
          rel="noopener noreferrer"
          className="ml-auto flex items-center gap-1 text-xs font-normal text-violet-300 hover:text-violet-200"
        >
          Get a free key <ExternalLink className="h-3 w-3" />
        </a>
      </label>
      <div className="flex items-center rounded-xl border border-white/10 bg-white/[0.03] transition focus-within:border-violet-400/60">
        <input
          id="api-key"
          type={visible ? "text" : "password"}
          value={apiKey}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Paste your key, e.g. AIza…"
          autoComplete="off"
          spellCheck={false}
          className="min-w-0 flex-1 bg-transparent px-3 py-2.5 font-mono text-sm outline-none placeholder:font-sans placeholder:text-white/30 disabled:opacity-60"
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Hide API key" : "Show API key"}
          className="grid h-9 w-9 place-items-center text-white/45 hover:text-white"
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      <label className="mt-2 flex items-center gap-2 text-xs text-white/50">
        <input
          type="checkbox"
          checked={remember}
          disabled={disabled}
          onChange={(e) => onRememberChange(e.target.checked)}
          className="h-3.5 w-3.5 accent-violet-500"
        />
        Remember on this device
      </label>
      {hasKey ? (
        <p className="mt-1.5 text-xs text-white/40">
          Used only for your own jobs: sent with the upload, never stored on the server or shown in results.
        </p>
      ) : demoWithoutKey ? (
        <p className="mt-2 flex gap-1.5 rounded-lg border border-amber-400/25 bg-amber-400/10 px-2.5 py-2 text-xs text-amber-100/90">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-300" />
          <span>
            Without a key you&apos;ll get <b>sample (dummy) data</b>, not data read from your documents. Add your Gemini key to
            extract real data.
          </span>
        </p>
      ) : (
        <p className="mt-1.5 text-xs text-white/40">Leave empty to use the server&apos;s own key.</p>
      )}
    </div>
  );
}
