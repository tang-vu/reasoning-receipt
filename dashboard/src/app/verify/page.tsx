import type { Metadata } from "next";

import { OfflineVerifier } from "@/components/offline-verifier";

export const metadata: Metadata = {
  title: "Verify a receipt — offline",
  description:
    "Paste or upload a reasoning-receipt/1 document and verify it entirely in your browser: " +
    "canonical bytes, node hashes, Merkle root, receipt hash, and Ed25519 signatures. " +
    "No server, no chain, no trust in us.",
  alternates: { canonical: "/verify/" },
};

export default function VerifyPage() {
  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">Offline receipt verification</h1>
        <p className="max-w-3xl text-muted">
          A <code className="font-mono text-accent">reasoning-receipt/1</code> document is
          self-verifying: every node hashes independently, the leaves fold into one Merkle
          root, and the root commits to the receipt hash. Paste a receipt below — verification
          runs entirely in this tab. Nothing is uploaded, fetched, or anchored; a broken
          network changes nothing about the answer.
        </p>
      </header>

      <OfflineVerifier />

      <section className="max-w-3xl space-y-2 text-sm text-muted">
        <h2 className="text-base font-semibold text-ink">What “verified” means here</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <strong className="text-ink">Integrity verified</strong> — the document is canonical,
            every declared hash matches recomputed leaves, and the Merkle root folds correctly.
          </li>
          <li>
            <strong className="text-ink">Signature verified</strong> (when present) — an Ed25519
            key signed the receipt hash or a node leaf. It proves key possession, not truth.
          </li>
          <li>
            <strong className="text-ink">Not proven</strong> — that the evidence is true, that
            the signer is who they claim, or that any anchor exists. Those are separate checks.
          </li>
        </ul>
        <p>
          Same checks as <code className="font-mono text-accent">rr verify</code>, the portable
          API, and the GitHub Action — one corpus, one result.
        </p>
      </section>
    </div>
  );
}
