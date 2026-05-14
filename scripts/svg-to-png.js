#!/usr/bin/env node
/**
 * svg-to-png.js — render an SVG file to a PNG at fixed dimensions.
 *
 * Required because some social-card consumers (iOS Messages, Telegram, a few
 * Discord clients) reject SVG `og:image` and silently drop the preview. PNG
 * is the universal format; we keep the SVG too so search engines that DO
 * support vector get the sharper version.
 *
 * Usage:
 *   node scripts/svg-to-png.js <input.svg> <output.png> [width] [height]
 *
 * Default: 1200×630, matching the OG card aspect ratio.
 */

const fs = require("node:fs");
const path = require("node:path");

// `sharp` is a heavyweight native dep we don't want to install at repo root.
// It already lives in dashboard/node_modules (Next.js installs it for image
// optimisation), so resolve from there.
const sharp = require(path.resolve(__dirname, "..", "dashboard", "node_modules", "sharp"));

async function main() {
  const [, , inputArg, outputArg, w, h] = process.argv;
  if (!inputArg || !outputArg) {
    console.error("usage: node scripts/svg-to-png.js <input.svg> <output.png> [width] [height]");
    process.exit(2);
  }
  const width = Number(w || 1200);
  const height = Number(h || 630);
  const inputPath = path.resolve(inputArg);
  const outputPath = path.resolve(outputArg);
  const svg = fs.readFileSync(inputPath);
  await sharp(svg, { density: 300 }).resize(width, height).png({ compressionLevel: 9 }).toFile(outputPath);
  const stat = fs.statSync(outputPath);
  console.log(`wrote ${outputPath} (${width}x${height}, ${(stat.size / 1024).toFixed(1)} KB)`);
}

main().catch((err) => {
  console.error("svg-to-png failed:", err.message);
  process.exit(1);
});
