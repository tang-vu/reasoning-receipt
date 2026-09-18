"use client";

import { useRef, useState } from "react";

import {
  ReceiptBuilder,
  verifyAny,
} from "@/vendor/rr-sdk/index.js";
import type { JsonValue, VerifyReport } from "@/vendor/rr-sdk/index.js";

/** Build a small domain-neutral receipt entirely in the browser. */
function buildSampleDocument(): Record<string, JsonValue> {
  const receipt = new ReceiptBuilder("demo:offline-verify", {
    tool: "rrtrace.xyz/verify",
  })
    .add("intent", "intent", { text: "Summarize Q3 support tickets" })
    .add("policy", "policy", { name: "no-pii-export", version: 2 })
    .add("evidence", "evidence", { source: "ticket-dump.json", rows: 1841 })
    .add("decision", "decision", { outcome: "approved", rationale: "aggregate stats only" })
    .link("intent", "policy", "evaluated_against")
    .link("decision", "evidence", "supported_by")
    .link("decision", "intent", "produced_by")
    .finalize({ receipt_id: "demo-offline-0001", produced_at: "2026-01-01T00:00:00Z" });
  return receipt.toDict();
}

interface LoadedDoc {
  /** Canonical pristine text used for verify + restore. */
  pristine: string;
  /** Current textarea contents (may be tampered). */
  text: string;
}

export function OfflineVerifier() {
  const [doc, setDoc] = useState<LoadedDoc | null>(null);
  const [report, setReport] = useState<VerifyReport | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [tampered, setTampered] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function loadText(text: string) {
    setDoc({ pristine: text, text });
    setTampered(false);
    runVerify(text);
  }

  function runVerify(text: string) {
    setParseError(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      setReport(null);
      setParseError(e instanceof Error ? e.message : String(e));
      return;
    }
    try {
      setReport(verifyAny(parsed));
    } catch (e) {
      setReport(null);
      setParseError(e instanceof Error ? e.message : String(e));
    }
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    loadText(await f.text());
    e.target.value = "";
  }

  /** Flip one character inside the first node payload — one byte, whole receipt fails. */
  function tamper() {
    if (!doc) return;
    let mutated = doc.pristine;
    try {
      const parsed = JSON.parse(doc.pristine) as {
        nodes?: { payload?: Record<string, unknown> }[];
      };
      const payload = parsed.nodes?.[0]?.payload;
      if (payload && typeof payload === "object" && Object.keys(payload).length > 0) {
        const key = Object.keys(payload)[0];
        const v = payload[key];
        payload[key] = typeof v === "number" ? v + 1 : typeof v === "string" ? `${v}X` : null;
        mutated = JSON.stringify(parsed, null, 2);
      } else {
        // Fallback: flip the last hex digit of the merkle_root.
        const j = mutated.indexOf("0x", mutated.lastIndexOf("merkle_root"));
        if (j >= 0) {
          const k = j + 2 + 63;
          mutated = mutated.slice(0, k) + (mutated[k] === "0" ? "1" : "0") + mutated.slice(k + 1);
        }
      }
    } catch {
      /* unparseable input — leave mutated = pristine, verify will flag it */
    }
    setDoc({ ...doc, text: mutated });
    setTampered(true);
    runVerify(mutated);
  }

  function restore() {
    if (!doc) return;
    setDoc({ ...doc, text: doc.pristine });
    setTampered(false);
    runVerify(doc.pristine);
  }

  return (
    <div className="space-y-5">
      {/* input row */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => loadText(JSON.stringify(buildSampleDocument(), null, 2))}
          className="border border-lime bg-lime px-4 py-2 font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-1 transition hover:opacity-85"
        >
          Build demo receipt
        </button>
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="border border-ink-3 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.12em] text-bone-dim transition hover:border-bone-faint hover:text-bone"
        >
          Upload .json
        </button>
        <input ref={fileRef} type="file" accept=".json,application/json" className="hidden" onChange={onFile} />
        {doc && (
          <>
            <button
              type="button"
              onClick={tamper}
              disabled={tampered}
              className="border border-red-500/60 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.12em] text-red-300 transition hover:bg-red-500/10 disabled:opacity-40"
            >
              Tamper one byte
            </button>
            <button
              type="button"
              onClick={restore}
              disabled={!tampered}
              className="border border-ink-3 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.12em] text-bone-dim transition hover:border-bone-faint hover:text-bone disabled:opacity-40"
            >
              Restore
            </button>
          </>
        )}
        <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.14em] text-bone-faint">
          runs 100% client-side
        </span>
      </div>

      {/* editor + verdict */}
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="space-y-2">
          <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-bone-faint">
            receipt document (editable — tamper here too)
          </label>
          <textarea
            value={doc?.text ?? ""}
            onChange={(e) => {
              const text = e.target.value;
              setDoc((d) => (d ? { ...d, text } : { pristine: text, text }));
              setTampered(doc ? text !== doc.pristine : false);
              runVerify(text);
            }}
            spellCheck={false}
            placeholder='{"schema_version": "reasoning-receipt/1", …}'
            className="h-[26rem] w-full resize-y border border-ink-3 bg-ink-1 p-3 font-mono text-xs leading-relaxed text-bone outline-none placeholder:text-bone-faint focus:border-lime"
          />
        </div>

        <div className="space-y-3">
          {parseError && (
            <div className="border border-red-500/60 bg-red-500/10 p-3 font-mono text-xs text-red-300">
              JSON parse error — {parseError}
            </div>
          )}
          {report ? <ReportPanel report={report} /> : !parseError && <EmptyPanel />}
        </div>
      </div>
    </div>
  );
}

function EmptyPanel() {
  return (
    <div className="grid h-full min-h-40 place-items-center border border-dashed border-ink-3 p-6 text-center font-mono text-xs text-bone-faint">
      Build a demo receipt, upload a file, or paste a document to verify it locally.
    </div>
  );
}

function ReportPanel({ report }: { report: VerifyReport }) {
  return (
    <div className="space-y-4">
      {/* verdict banner */}
      <div
        className={`flex items-center justify-between border px-4 py-3 ${
          report.valid ? "border-lime bg-lime-soft" : "border-red-500/60 bg-red-500/10"
        }`}
      >
        <span
          className={`font-mono text-sm font-bold uppercase tracking-[0.16em] ${
            report.valid ? "text-lime" : "text-red-300"
          }`}
        >
          {report.valid ? "✓ valid" : "✗ invalid"}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-bone-dim">
          {report.variant}
        </span>
      </div>

      {/* identity */}
      <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <KV k="schema" v={report.schema_version} />
        <KV k="canonicalization" v={report.canonicalization} />
        <KV k="nodes" v={String(report.node_count)} />
        <KV k="edges" v={String(report.edge_count)} />
      </div>

      {/* checks */}
      <div>
        <h3 className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-bone-faint">
          checks
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(report.checks).map(([name, ok]) => (
            <span
              key={name}
              className={`border px-2 py-1 font-mono text-[11px] ${
                ok
                  ? "border-lime/50 text-lime"
                  : "border-red-500/60 bg-red-500/10 text-red-300"
              }`}
            >
              {ok ? "✓" : "✗"} {name}
            </span>
          ))}
        </div>
      </div>

      {/* hashes */}
      {(report.receipt_hash || report.merkle_root) && (
        <div className="space-y-1.5">
          {report.receipt_hash && <HashRow label="receipt_hash" value={report.receipt_hash} />}
          {report.merkle_root && <HashRow label="merkle_root" value={report.merkle_root} />}
        </div>
      )}

      {/* signatures */}
      {report.signatures.length > 0 && (
        <div>
          <h3 className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-bone-faint">
            signatures — key possession only, not truth
          </h3>
          <div className="space-y-1.5">
            {report.signatures.map((s, i) => (
              <div
                key={i}
                className={`flex items-center gap-3 border px-3 py-2 font-mono text-[11px] ${
                  s.valid ? "border-ink-3 text-bone-dim" : "border-red-500/60 bg-red-500/10 text-red-300"
                }`}
              >
                <span className={s.valid ? "text-lime" : "text-red-300"}>{s.valid ? "✓" : "✗"}</span>
                <span className="text-bone">{String(s.scope ?? "?")}</span>
                <span className="truncate text-bone-faint">{String(s.public_key ?? "")}</span>
                {typeof s.reason === "string" && <span className="ml-auto">{s.reason}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* errors */}
      {report.errors.length > 0 && (
        <div>
          <h3 className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-red-300">
            errors
          </h3>
          <ul className="space-y-1 border border-red-500/40 bg-red-500/5 p-3 font-mono text-[11px] text-red-200">
            {report.errors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <div className="border border-ink-3 bg-ink-1 px-3 py-2">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-bone-faint">{k}</div>
      <div className="truncate font-mono text-[11px] text-bone" title={v}>
        {v}
      </div>
    </div>
  );
}

function HashRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-3 border border-ink-3 bg-ink-1 px-3 py-2">
      <span className="w-24 flex-none font-mono text-[10px] uppercase tracking-[0.12em] text-bone-faint">
        {label}
      </span>
      <code className="truncate font-mono text-[11px] text-bone" title={value}>
        {value}
      </code>
    </div>
  );
}
