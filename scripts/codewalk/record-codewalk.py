"""record-codewalk.py — capture the Circle codebase-walkthrough panels.

Opens scripts/codewalk/codewalk.html (a self-contained page with one full-
viewport panel per Circle product) in Playwright, dwells on each panel long
enough to read the code + note, and records a single 1080p webm. Converts to
mp4 with the Playwright-bundled ffmpeg.

This is the "codebase walkthrough" half of the Circle grant video; the live
dashboard tour (scripts/record-demo-web.py) is the "integration demo" half.

Usage:
    python -m scripts.codewalk.record-codewalk
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = HERE / "codewalk.html"
PW_FFMPEG = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright" / "ffmpeg-1011" / "ffmpeg-win64.exe"

# Number of full-viewport panels in codewalk.html. Each is dwelled on for
# DWELL_MS so the narration/subtitle for that Circle product has time to land.
N_PANELS = 7
DWELL_MS = 9000


def run(out_dir: Path) -> Path:
    from playwright.sync_api import sync_playwright

    seg = out_dir / "segments"
    seg.mkdir(parents=True, exist_ok=True)
    for old in seg.glob("*.webm"):
        old.unlink(missing_ok=True)

    url = PAGE.as_uri()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(seg),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        # Step through each panel: scroll it to the top of the viewport, dwell.
        for i in range(N_PANELS):
            page.evaluate(
                "(i) => { const p = document.querySelectorAll('.panel')[i];"
                " if (p) p.scrollIntoView({behavior:'smooth', block:'start'}); }",
                i,
            )
            page.wait_for_timeout(DWELL_MS)
        page.wait_for_timeout(800)
        ctx.close()
        browser.close()

    webms = sorted(seg.glob("*.webm"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not webms:
        sys.exit("[codewalk] no webm produced")
    return webms[0]


def to_mp4(webm: Path, mp4: Path, ffmpeg: Path) -> bool:
    if not ffmpeg.exists():
        print(f"[codewalk] ffmpeg not at {ffmpeg}; leaving webm only", flush=True)
        return False
    cmd = [str(ffmpeg), "-y", "-i", str(webm), "-c:v", "libx264",
           "-crf", "22", "-preset", "fast", "-pix_fmt", "yuv420p", str(mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[codewalk] ffmpeg failed:\n{r.stderr[-500:]}", flush=True)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Record the Circle codebase walkthrough.")
    p.add_argument("--out", default="recordings")
    p.add_argument("--ffmpeg", default=str(PW_FFMPEG))
    args = p.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    webm = run(out_dir)
    final = out_dir / "codewalk.webm"
    if webm.resolve() != final.resolve():
        if final.exists():
            final.unlink()
        webm.rename(final)
    print(f"[codewalk] webm -> {final}  ({final.stat().st_size / 1_000_000:.1f} MB)", flush=True)

    mp4 = out_dir / "codewalk.mp4"
    if to_mp4(final, mp4, Path(args.ffmpeg)):
        print(f"[codewalk] mp4  -> {mp4}  ({mp4.stat().st_size / 1_000_000:.1f} MB)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
