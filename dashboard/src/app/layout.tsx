import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "ReasoningReceipt — Oracle dashboard",
  description:
    "Public dashboard for ReasoningReceipt — an x402-paywalled prediction-market oracle settled on Arc.",
};

const nav = [
  { href: "/", label: "Home" },
  { href: "/agents", label: "Agents" },
  { href: "/try", label: "Try it" },
  { href: "/traces", label: "Traces" },
  { href: "/calibration", label: "Calibration" },
  { href: "/stats", label: "Stats" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg text-ink">
        <header className="border-b border-border">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <Link href="/" className="font-semibold tracking-tight">
              ReasoningReceipt <span className="text-muted">·</span>
              <span className="ml-1 text-accent">oracle</span>
            </Link>
            <nav className="flex gap-5 text-sm text-muted">
              {nav.map((n) => (
                <Link key={n.href} href={n.href} className="hover:text-ink">
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
        <footer className="mt-16 border-t border-border">
          <div className="mx-auto max-w-6xl px-6 py-6 text-xs text-muted">
            Settled on Arc testnet · per-receipt cost ≈ $0.01 · traces pinned to Irys
          </div>
        </footer>
      </body>
    </html>
  );
}
