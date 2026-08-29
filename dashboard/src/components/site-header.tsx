"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const nav = [
  { href: "/build", label: "Build" },
  { href: "/agents", label: "Agents" },
  { href: "/inclusion", label: "Verify" },
  { href: "/traces", label: "Traces" },
  { href: "/stats", label: "Stats" },
];

export function SiteHeader() {
  const path = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-ink-3 backdrop-blur-xl" style={{ background: "color-mix(in oklab, var(--ink) 90%, transparent)" }}>
      <div className="mx-auto flex h-[64px] w-full min-w-0 max-w-[1480px] items-center gap-5 overflow-hidden px-4 sm:px-6 lg:px-8">
        <Link href="/" className="group flex min-w-0 items-center gap-3" onClick={() => setOpen(false)}>
          <span className="relative grid h-9 w-9 flex-none place-items-center border border-bone/70 font-display text-xl italic transition-colors group-hover:border-lime group-hover:text-lime">
            R<i className="absolute -bottom-px -right-px h-2 w-2 bg-lime" aria-hidden />
          </span>
          <span className="min-w-0">
            <span className="block truncate font-mono text-[12px] font-semibold tracking-[0.015em] text-bone sm:text-[13px]">ReasoningReceipt</span>
            <span className="hidden font-mono text-[8px] uppercase tracking-[0.22em] text-bone-faint sm:block">proof infrastructure for AI</span>
          </span>
        </Link>

        <div className="ml-auto hidden items-center gap-2 border-l border-ink-3 pl-5 lg:flex">
          <span className="h-1.5 w-1.5 rounded-full bg-lime" style={{ animation: "pulse-ring 1.8s ease-out infinite" }} />
          <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-bone-faint">system online</span>
        </div>

        <nav className="ml-2 hidden items-center gap-1 md:flex">
          {nav.map((item, index) => {
            const active = path === item.href || path.startsWith(`${item.href}/`);
            return (
              <Link key={item.href} href={item.href} className={`group relative px-3 py-2 font-mono text-[10px] uppercase tracking-[0.12em] transition-colors ${active ? "text-lime" : "text-bone-dim hover:text-bone"}`}>
                <span className="mr-1 text-[8px] text-bone-faint">0{index + 1}</span>{item.label}
                {active && <span className="absolute inset-x-3 -bottom-[13px] h-px bg-lime" />}
              </Link>
            );
          })}
        </nav>

        <Link href="/build#lab" className="ml-auto hidden flex-none items-center gap-2 border border-lime bg-lime px-4 py-2.5 font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-1 transition-all hover:-translate-y-0.5 hover:bg-bone md:inline-flex">
          Mint a proof <span aria-hidden>↗</span>
        </Link>

        <button type="button" onClick={() => setOpen((value) => !value)} className="relative z-10 ml-auto grid h-9 w-10 flex-none place-items-center border border-ink-3 font-mono text-xs text-bone md:hidden" aria-expanded={open} aria-label="Toggle navigation">
          {open ? "×" : "≡"}
        </button>
      </div>

      {open && (
        <nav className="grid border-t border-ink-3 bg-ink-1 px-4 py-3 md:hidden">
          {nav.map((item, index) => (
            <Link key={item.href} href={item.href} onClick={() => setOpen(false)} className="flex items-center justify-between border-b border-ink-3 py-3 font-mono text-xs uppercase tracking-[0.12em] text-bone-dim last:border-0">
              <span><i className="mr-3 not-italic text-bone-faint">0{index + 1}</i>{item.label}</span><span className="text-lime">→</span>
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
