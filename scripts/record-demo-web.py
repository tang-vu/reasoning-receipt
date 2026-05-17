"""record-demo-web.py — Windows-friendly product demo capture.

Single-context Playwright tour of the live dashboard. Outputs a single
1080p webm (which YouTube + most submission forms accept) and an mp4 if
the Playwright-bundled ffmpeg is available. No asciinema, no system
ffmpeg, no daemon required — visits the public dashboard only.

Usage:
    uv run python -m scripts.record-demo-web \\
        --dashboard https://rrtrace.xyz --v3-trace-id 4553
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PW_FFMPEG_DEFAULT = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright" / "ffmpeg-1011" / "ffmpeg-win64.exe"

# (path, post-load wait ms). wait_ms is tuned so per-page duration matches
# the corresponding narration segment from generate-demo-narration.py:
#   home 11.2s | traces 13.5s | trace-detail 23.3s | calibration 10.4s |
#   try-live 13.4s | inclusion 24.2s. Total ~96s, same as the narration WAV.
# Subtract ~5.7s of fixed overhead (goto + 1.5s post-load + ~2.7s scrolls).
DEFAULT_TOUR = [
    ("/", 5500),
    ("/traces", 7700),
    ("/traces/{v3}", 17500),
    ("/calibration", 4600),
    ("/try-live", 7600),
    ("/inclusion", 18500),
]


def run_tour(dashboard: str, v3_trace_id: int | None, out_dir: Path) -> Path:
    from playwright.sync_api import sync_playwright

    seg_dir = out_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    # clear any previous segments so we pick the new webm unambiguously
    for old in seg_dir.glob("*.webm"):
        old.unlink(missing_ok=True)

    tour = [
        (p.replace("{v3}", str(v3_trace_id)) if v3_trace_id else p, w)
        for p, w in DEFAULT_TOUR
        if "{v3}" not in p or v3_trace_id is not None
    ]

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(seg_dir),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = ctx.new_page()
        for path, wait_ms in tour:
            url = f"{dashboard.rstrip('/')}{path}"
            print(f"[record] -> {url}", flush=True)
            try:
                # `domcontentloaded` (not `networkidle`) — the home page has
                # an SSE stream that never closes, so networkidle always
                # times out and wastes 30s. DOM + a fixed post-wait is enough.
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:  # noqa: BLE001
                print(f"[record]   goto timed out: {exc}; continuing anyway", flush=True)
            page.wait_for_timeout(1500)
            # scroll halfway and back for visual motion
            for _ in range(6):
                page.mouse.wheel(0, 280)
                page.wait_for_timeout(220)
            page.wait_for_timeout(wait_ms)
            for _ in range(4):
                page.mouse.wheel(0, -360)
                page.wait_for_timeout(180)
        ctx.close()
        browser.close()

    webms = sorted(seg_dir.glob("*.webm"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not webms:
        sys.exit("[record] no webm produced — Playwright did not record")
    return webms[0]


def convert_to_mp4(webm: Path, mp4: Path, ffmpeg: Path) -> bool:
    if not ffmpeg.exists():
        print(f"[record] ffmpeg not at {ffmpeg}; skipping mp4 conversion", flush=True)
        return False
    cmd = [
        str(ffmpeg), "-y", "-i", str(webm),
        "-c:v", "libx264", "-crf", "22", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        str(mp4),
    ]
    print(f"[record] converting -> {mp4}", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[record] ffmpeg failed (rc={r.returncode}):\n{r.stderr[-600:]}", flush=True)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Record dashboard tour (Windows-friendly).")
    p.add_argument("--dashboard", default="https://rrtrace.xyz")
    p.add_argument("--v3-trace-id", type=int, default=None,
                   help="receipt id of an rr-trace/3 row — featured in the tour")
    p.add_argument("--out", default="recordings", help="output directory")
    p.add_argument("--ffmpeg", default=str(PW_FFMPEG_DEFAULT),
                   help="path to ffmpeg.exe (default: playwright-bundled)")
    args = p.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    webm = run_tour(args.dashboard, args.v3_trace_id, out_dir)
    final_webm = out_dir / "demo.webm"
    if webm.resolve() != final_webm.resolve():
        if final_webm.exists():
            final_webm.unlink()
        webm.rename(final_webm)
    print(f"[record] webm -> {final_webm}  ({final_webm.stat().st_size / 1_000_000:.1f} MB)", flush=True)

    mp4 = out_dir / "demo.mp4"
    if convert_to_mp4(final_webm, mp4, Path(args.ffmpeg)):
        print(f"[record] mp4  -> {mp4}  ({mp4.stat().st_size / 1_000_000:.1f} MB)", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
