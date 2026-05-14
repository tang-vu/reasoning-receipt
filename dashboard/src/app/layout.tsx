import type { Metadata, Viewport } from "next";
import Link from "next/link";
import Script from "next/script";
import "./globals.css";

const SITE_URL = "https://rrtrace.xyz";
const SITE_NAME = "ReasoningReceipt";
// 130 chars — Open Graph / Twitter Card sweet spot is 110-160.
const SITE_DESC =
  "x402-paywalled AI oracle for prediction markets. Every price ships with a byte-verifiable reasoning trace, Merkle-rooted on Arc.";
// 55 chars — title sweet spot is 50-60. Same value for HTML <title>,
// OG title, and Twitter title so previews are consistent everywhere.
const SITE_TITLE = "ReasoningReceipt — Byte-verifiable AI oracle on Arc";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: SITE_TITLE,
    template: `%s · ${SITE_NAME}`,
  },
  description: SITE_DESC,
  applicationName: SITE_NAME,
  authors: [{ name: "Vu Minh Tang", url: "https://github.com/tang-vu" }],
  generator: "Next.js",
  keywords: [
    "x402",
    "prediction market oracle",
    "Arc Testnet",
    "Circle",
    "USDC",
    "Merkle DAG",
    "verifiable reasoning",
    "AI agent",
    "Polymarket",
    "Kalshi",
    "ReasoningReceipt",
    "byte-verifiable trace",
    "Agora hackathon",
    "Canteen",
  ],
  category: "technology",
  alternates: {
    canonical: "/",
  },
  manifest: "/site.webmanifest",
  icons: {
    icon: [
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/favicon-192.png", type: "image/png", sizes: "192x192" },
      { url: "/favicon-512.png", type: "image/png", sizes: "512x512" },
    ],
    shortcut: "/favicon.svg",
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: SITE_NAME,
    title: SITE_TITLE,
    description: SITE_DESC,
    locale: "en_US",
    images: [
      // PNG primary — universal social-card support (iOS Messages, Telegram, etc).
      {
        url: "/og-banner.png",
        width: 1200,
        height: 630,
        alt: "ReasoningReceipt — Five agents debate. Supervisor merges. Critic audits. Merkle-rooted reasoning DAG on Arc.",
        type: "image/png",
      },
      // SVG fallback for crawlers that prefer vector.
      {
        url: "/og-banner.svg",
        width: 1200,
        height: 630,
        alt: "ReasoningReceipt — Five agents debate. Supervisor merges. Critic audits. Merkle-rooted reasoning DAG on Arc.",
        type: "image/svg+xml",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    site: "@tangvu_dev",
    creator: "@tangvu_dev",
    title: SITE_TITLE,
    description: SITE_DESC,
    images: ["/og-banner.png"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
  other: {
    // Surfaces an AI-readable digest per https://llmstxt.org/
    "llms-txt": `${SITE_URL}/llms.txt`,
  },
};

export const viewport: Viewport = {
  themeColor: "#0a0a0b",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
};

const nav = [
  { href: "/", label: "Home" },
  { href: "/agents", label: "Agents" },
  { href: "/try", label: "Try it" },
  { href: "/traces", label: "Traces" },
  { href: "/calibration", label: "Calibration" },
  { href: "/stats", label: "Stats" },
];

const structuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebSite",
      "@id": `${SITE_URL}/#website`,
      url: SITE_URL,
      name: SITE_NAME,
      description: SITE_DESC,
      publisher: { "@id": `${SITE_URL}/#person` },
      inLanguage: "en",
    },
    {
      "@type": "Person",
      "@id": `${SITE_URL}/#person`,
      name: "Vu Minh Tang",
      url: "https://github.com/tang-vu",
      sameAs: ["https://github.com/tang-vu", "https://x.com/tangvu_dev"],
    },
    {
      "@type": "SoftwareApplication",
      name: SITE_NAME,
      applicationCategory: "DeveloperApplication",
      operatingSystem: "Web",
      url: SITE_URL,
      codeRepository: "https://github.com/tang-vu/reasoning-receipt",
      programmingLanguage: ["Python", "TypeScript", "Solidity"],
      offers: {
        "@type": "Offer",
        price: "0.01",
        priceCurrency: "USDC",
        description: "Per paid query via x402 v2 on Arc Testnet",
      },
      description: SITE_DESC,
    },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg text-ink">
        <Script
          id="structured-data"
          type="application/ld+json"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
        />
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
          <div className="mx-auto flex max-w-6xl flex-wrap items-baseline justify-between gap-3 px-6 py-6 text-xs text-muted">
            <div>
              Settled on Arc testnet · per-receipt cost ≈ $0.01 · traces pinned to Irys
            </div>
            <div className="flex gap-4">
              <a href="https://github.com/tang-vu/reasoning-receipt" rel="noopener" className="hover:text-ink">GitHub</a>
              <a href="https://testnet.arcscan.app/address/0x27d93c52fea923f956345af27f61d7bf47f0c4c1" rel="noopener" className="hover:text-ink">Contract V2</a>
              <a href="/llms.txt" className="hover:text-ink">llms.txt</a>
              <a href="/sitemap.xml" className="hover:text-ink">Sitemap</a>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
