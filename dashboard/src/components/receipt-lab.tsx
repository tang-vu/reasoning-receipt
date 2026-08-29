"use client";

import { useMemo, useState } from "react";

type DraftNode = { id: string; kind: string; payload: string };
type ReceiptResult = Record<string, unknown> & {
  receipt_id?: string;
  receipt_hash?: string;
  merkle_root?: string;
  nodes?: Array<Record<string, unknown>>;
};

const presets: Record<string, { subject: string; nodes: DraftNode[] }> = {
  refund: {
    subject: "support:refund-approval",
    nodes: [
      { id: "intent", kind: "request", payload: '{ "refund_usd": 49, "reason": "late delivery" }' },
      { id: "policy", kind: "policy", payload: '{ "auto_approve_below_usd": 100 }' },
      { id: "decision", kind: "outcome", payload: '{ "approved": true }' },
    ],
  },
  agent: {
    subject: "agent:production-deploy",
    nodes: [
      { id: "intent", kind: "instruction", payload: '{ "goal": "deploy release", "environment": "production" }' },
      { id: "tool", kind: "tool_call", payload: '{ "name": "vercel.deploy", "target": "production" }' },
      { id: "approval", kind: "human_approval", payload: '{ "approved_by": "operator", "scope": "release" }' },
      { id: "result", kind: "outcome", payload: '{ "status": "ready", "checks_passed": true }' },
    ],
  },
  access: {
    subject: "security:temporary-access",
    nodes: [
      { id: "request", kind: "request", payload: '{ "role": "analyst", "duration_hours": 4 }' },
      { id: "risk", kind: "evaluation", payload: '{ "risk": "low", "mfa": true }' },
      { id: "rule", kind: "policy", payload: '{ "max_hours": 8, "requires_mfa": true }' },
      { id: "grant", kind: "outcome", payload: '{ "granted": true, "expires_automatically": true }' },
    ],
  },
};

const API_BASE = process.env.NEXT_PUBLIC_LIVE_API_BASE || "/api";

export function ReceiptLab() {
  const [subject, setSubject] = useState(presets.refund.subject);
  const [nodes, setNodes] = useState<DraftNode[]>(presets.refund.nodes);
  const [result, setResult] = useState<ReceiptResult | null>(null);
  const [verified, setVerified] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const validPayloads = useMemo(() => nodes.every((node) => {
    try { JSON.parse(node.payload); return true; } catch { return false; }
  }), [nodes]);

  function loadPreset(key: string) {
    const preset = presets[key];
    setSubject(preset.subject);
    setNodes(preset.nodes.map((node) => ({ ...node })));
    setResult(null);
    setVerified(null);
    setError("");
  }

  function updateNode(index: number, patch: Partial<DraftNode>) {
    setNodes((current) => current.map((node, nodeIndex) => nodeIndex === index ? { ...node, ...patch } : node));
  }

  async function createReceipt() {
    setBusy(true);
    setError("");
    setVerified(null);
    try {
      const response = await fetch(`${API_BASE}/v1/receipts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject,
          metadata: { created_with: "rrtrace.xyz/lab" },
          nodes: nodes.map((node) => ({ id: node.id, kind: node.kind, payload: JSON.parse(node.payload) })),
        }),
      });
      if (!response.ok) throw new Error(`Create failed (${response.status})`);
      const receipt = await response.json() as ReceiptResult;
      setResult(receipt);

      const envelope = { ...receipt };
      delete envelope.receipt_hash;
      const verifyResponse = await fetch(`${API_BASE}/v1/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ receipt: envelope }),
      });
      if (!verifyResponse.ok) throw new Error(`Verify failed (${verifyResponse.status})`);
      const verification = await verifyResponse.json() as { valid: boolean };
      setVerified(verification.valid);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create receipt");
    } finally {
      setBusy(false);
    }
  }

  async function copyResult() {
    if (!result) return;
    await navigator.clipboard.writeText(JSON.stringify(result, null, 2));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <section id="lab" className="scroll-mt-24 border border-ink-3 bg-ink-1">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-ink-3 px-5 py-4 sm:px-7">
        <div className="flex items-center gap-3"><span className="h-2 w-2 bg-lime" /><span className="font-mono text-[10px] uppercase tracking-[0.16em] text-bone">Receipt lab / live API</span></div>
        <div className="font-mono text-[8px] uppercase tracking-[0.15em] text-bone-faint">No wallet · No sign-in · No chain</div>
      </div>

      <div className="grid lg:grid-cols-[1.05fr_0.95fr]">
        <div className="border-b border-ink-3 p-5 sm:p-7 lg:border-b-0 lg:border-r">
          <div className="mb-7 flex flex-wrap gap-2">
            {Object.keys(presets).map((key, index) => (
              <button key={key} type="button" onClick={() => loadPreset(key)} className="border border-ink-3 px-3 py-2 font-mono text-[9px] uppercase tracking-[0.12em] text-bone-dim transition-colors hover:border-lime hover:text-lime">0{index + 1} / {key}</button>
            ))}
          </div>

          <label className="block">
            <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-bone-faint">Decision subject</span>
            <input value={subject} onChange={(event) => setSubject(event.target.value)} className="mt-2 w-full border border-ink-3 bg-ink-2 px-4 py-3 font-mono text-xs text-bone outline-none transition-colors focus:border-lime" />
          </label>

          <div className="mt-7 space-y-3">
            {nodes.map((node, index) => {
              let payloadValid = true;
              try { JSON.parse(node.payload); } catch { payloadValid = false; }
              return (
                <div key={`${index}-${node.id}`} className="proof-card border border-ink-3 bg-ink-2/40 p-4">
                  <div className="grid gap-3 sm:grid-cols-[42px_1fr_1fr]">
                    <span className="grid h-10 w-10 place-items-center rounded-full border border-lime/60 font-mono text-[9px] text-lime">{String(index + 1).padStart(2, "0")}</span>
                    <label><span className="font-mono text-[8px] uppercase tracking-[0.13em] text-bone-faint">Node id</span><input value={node.id} onChange={(event) => updateNode(index, { id: event.target.value })} className="mt-1.5 w-full border-b border-ink-3 bg-transparent pb-2 font-mono text-[11px] text-bone outline-none focus:border-lime" /></label>
                    <label><span className="font-mono text-[8px] uppercase tracking-[0.13em] text-bone-faint">Kind</span><input value={node.kind} onChange={(event) => updateNode(index, { kind: event.target.value })} className="mt-1.5 w-full border-b border-ink-3 bg-transparent pb-2 font-mono text-[11px] text-bone outline-none focus:border-lime" /></label>
                  </div>
                  <label className="mt-3 block"><span className={`font-mono text-[8px] uppercase tracking-[0.13em] ${payloadValid ? "text-bone-faint" : "text-terra"}`}>Payload JSON {payloadValid ? "✓" : "— invalid"}</span><textarea value={node.payload} onChange={(event) => updateNode(index, { payload: event.target.value })} rows={2} spellCheck={false} className="mt-1.5 w-full resize-y bg-transparent font-mono text-[10px] leading-5 text-bone-dim outline-none" /></label>
                </div>
              );
            })}
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button type="button" onClick={createReceipt} disabled={busy || !subject || !nodes.length || !validPayloads} className="inline-flex min-w-44 items-center justify-between gap-5 bg-lime px-5 py-3.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-1 transition-opacity disabled:cursor-not-allowed disabled:opacity-40">{busy ? "Hashing…" : "Create + verify"}<span>→</span></button>
            <span className="font-mono text-[8px] uppercase tracking-[0.12em] text-bone-faint">POST /v1/receipts → /v1/verify</span>
          </div>
          {error && <div className="mt-4 border border-terra/50 bg-terra-soft p-3 font-mono text-[10px] text-terra">{error}</div>}
        </div>

        <div className="relative min-h-[560px] overflow-hidden p-5 sm:p-7">
          <div className="instrument-grid pointer-events-none absolute inset-0 opacity-25" />
          <div className="relative flex items-center justify-between border-b border-ink-3 pb-4"><span className="font-mono text-[9px] uppercase tracking-[0.15em] text-bone-faint">Output artifact</span>{result && <button type="button" onClick={copyResult} className="font-mono text-[9px] uppercase tracking-[0.12em] text-lime">{copied ? "Copied ✓" : "Copy JSON"}</button>}</div>

          {!result ? (
            <div className="relative grid min-h-[460px] place-items-center text-center"><div><div className="mx-auto grid h-20 w-20 place-items-center rounded-full border border-dashed border-ink-3 font-display text-4xl italic text-bone-faint">R</div><div className="mt-6 font-mono text-[9px] uppercase tracking-[0.16em] text-bone-faint">Waiting for an action to prove</div></div></div>
          ) : (
            <div className="relative mt-6">
              <div className={`mb-5 flex items-center justify-between border p-4 ${verified ? "border-lime/50 bg-lime-soft" : "border-terra/50 bg-terra-soft"}`}><span className={`font-mono text-[10px] uppercase tracking-[0.16em] ${verified ? "text-lime" : "text-terra"}`}>{verified ? "Byte verification passed" : verified === false ? "Verification failed" : "Verifying…"}</span><span className="text-lg">{verified ? "✓" : "·"}</span></div>
              <ResultField label="schema" value={String(result.schema_version ?? "reasoning-receipt/1")} />
              <ResultField label="receipt_id" value={String(result.receipt_id ?? "—")} />
              <ResultField label="merkle_root" value={String(result.merkle_root ?? "—")} accent />
              <ResultField label="receipt_hash" value={String(result.receipt_hash ?? "—")} />
              <div className="mt-6 grid grid-cols-2 border border-ink-3"><div className="p-4"><div className="font-mono text-[8px] uppercase tracking-[0.14em] text-bone-faint">Nodes committed</div><div className="mt-2 font-display text-4xl italic">{result.nodes?.length ?? 0}</div></div><div className="border-l border-ink-3 p-4"><div className="font-mono text-[8px] uppercase tracking-[0.14em] text-bone-faint">Trust required</div><div className="mt-2 font-display text-4xl italic text-lime">Zero</div></div></div>
              <pre className="mt-6 max-h-56 overflow-auto border border-ink-3 bg-ink-2 p-4 font-mono text-[9px] leading-5 text-bone-faint"><code>{JSON.stringify(result, null, 2)}</code></pre>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function ResultField({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return <div className="border-b border-dotted border-ink-3 py-4"><div className="font-mono text-[8px] uppercase tracking-[0.14em] text-bone-faint">{label}</div><div className={`mt-1 break-all font-mono text-[10px] leading-5 ${accent ? "text-lime" : "text-bone-dim"}`}>{value}</div></div>;
}
