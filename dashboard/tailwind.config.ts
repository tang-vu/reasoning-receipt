import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["ui-monospace", "JetBrains Mono", "Menlo", "monospace"],
      },
      colors: {
        bg: "#0a0a0b",
        panel: "#111114",
        panel2: "#16161b",
        border: "#23232a",
        ink: "#e7e7ea",
        muted: "#8a8a93",
        accent: "#5eead4",
        accent2: "#fcd34d",
        danger: "#f87171",
      },
    },
  },
  plugins: [],
};
export default config;
