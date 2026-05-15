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
      // Tokens map onto the CSS-var palette in globals.css. Legacy semantic
      // in our pre-redesign code was `ink` = the primary *foreground* color,
      // `bg` = page background. The new design palette inverts the naming —
      // `--ink` is now the DARK background and `--bone` is the cream
      // foreground. To keep all existing `text-ink`/`bg-bg` usages working,
      // remap them here onto the design-spec roles.
      colors: {
        // foreground / text — was `text-ink` in legacy components
        ink: "var(--bone)",
        // background — was `bg-bg`
        bg: "var(--ink)",
        // design-native tokens (use these in new components)
        "ink-1": "var(--ink)",
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
