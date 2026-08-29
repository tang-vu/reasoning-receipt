import type { Metadata, Viewport } from "next";
import Script from "next/script";
import { Instrument_Serif, Inter, JetBrains_Mono } from "next/font/google";

import { Web3Provider } from "@/components/web3-provider";
import { SiteHeader } from "@/components/site-header";

import "./globals.css";

const serifDisplay = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
  variable: "--font-instrument-serif",
  display: "swap",
});
const bodySans = Inter({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-inter",
  display: "swap",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

const SITE_URL = "https://rrtrace.xyz";
const SITE_NAME = "ReasoningReceipt";
// 130 chars — Open Graph / Twitter Card sweet spot is 110-160.
const SITE_DESC =
  "Portable, byte-verifiable receipts for AI decisions and actions. Capture evidence, policy checks, tool calls, approvals, and outcomes.";
// 55 chars — title sweet spot is 50-60. Same value for HTML <title>,
// OG title, and Twitter title so previews are consistent everywhere.
const SITE_TITLE = "ReasoningReceipt — Verifiable receipts for AI decisions";

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
    "AI audit trail",
    "AI governance",
    "agent observability",
    "Merkle DAG",
    "verifiable reasoning",
    "AI agent",
    "ReasoningReceipt",
    "byte-verifiable trace",
    "portable receipt",
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
        alt: "ReasoningReceipt — Portable, byte-verifiable evidence for AI decisions and actions.",
        type: "image/png",
      },
      // SVG fallback for crawlers that prefer vector.
      {
        url: "/og-banner.svg",
        width: 1200,
        height: 630,
        alt: "ReasoningReceipt — Portable, byte-verifiable evidence for AI decisions and actions.",
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
      isAccessibleForFree: true,
      description: SITE_DESC,
    },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${serifDisplay.variable} ${bodySans.variable} ${mono.variable}`}
    >
      <body className="min-h-screen bg-bg text-bone">
        <Script
          id="structured-data"
          type="application/ld+json"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
        />
        <Web3Provider>
          <SiteHeader />
          <main className="mx-auto w-full min-w-0 max-w-[1480px] overflow-hidden px-4 sm:px-6 lg:px-8">{children}</main>
          <footer className="mt-12 border-t border-ink-3 sm:mt-16">
          <div className="mx-auto flex max-w-[1480px] flex-wrap items-baseline justify-between gap-3 px-4 py-6 text-[11px] text-bone-dim sm:px-6 sm:text-xs lg:px-8">
            <div>
              Open protocol · verify offline · optional Arc, Irys, and x402 adapters
            </div>
            <div className="flex flex-wrap gap-4">
              <a href="https://github.com/tang-vu/reasoning-receipt" rel="noopener" className="hover:text-bone">GitHub</a>
              <a href="https://testnet.arcscan.app/address/0x27d93c52fea923f956345af27f61d7bf47f0c4c1" rel="noopener" className="hover:text-bone">Contract V2</a>
              <a href="/llms.txt" className="hover:text-bone">llms.txt</a>
              <a href="/sitemap.xml" className="hover:text-bone">Sitemap</a>
            </div>
          </div>
        </footer>
        </Web3Provider>
      </body>
    </html>
  );
}
