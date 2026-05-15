import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        // Editorial / receipt vibe ported from design-landing/index.html.
        // Display = Instrument Serif (Google Fonts, loaded in layout.tsx).
        sans: ["var(--f-body)", "Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["var(--f-mono)", "JetBrains Mono", "ui-monospace", "Menlo", "monospace"],
        display: ["var(--f-display)", "Instrument Serif", "Times New Roman", "serif"],
      },
      // Tokens map onto the CSS-var palette in globals.css. Keeping the
      // legacy `bg`/`panel`/`accent` names so existing components compile;
      // values now resolve to the design's oklch palette.
      colors: {
        bg: "var(--ink)",
        ink: "var(--ink)",
        "ink-2": "var(--ink-2)",
        "ink-3": "var(--ink-3)",
        rule: "var(--rule)",
        bone: "var(--bone)",
        "bone-dim": "var(--bone-dim)",
        "bone-faint": "var(--bone-faint)",
        lime: "var(--lime)",
        "lime-soft": "var(--lime-soft)",
        terra: "var(--terra)",
        "terra-soft": "var(--terra-soft)",
        amber: "var(--amber)",
        // Compatibility aliases for components written against the old palette.
        panel: "var(--ink-2)",
        panel2: "var(--ink-3)",
        border: "var(--ink-3)",
        muted: "var(--bone-dim)",
        accent: "var(--lime)",
        accent2: "var(--amber)",
        danger: "var(--terra)",
      },
    },
  },
  plugins: [],
};
export default config;
