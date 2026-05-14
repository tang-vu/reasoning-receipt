"""record-demo.py — orchestrate the submission demo capture.

Records four segments:
  1. Agent loop (asciinema) — 30s
  2. demo-runner (asciinema) — 60s
  3. Dashboard pages (playwright headless screenshots → animated mp4) — 45s
  4. Arc explorer of the contract event log (playwright) — 30s

Stitches them with ffmpeg into a 1080p MP4 with burned-in captions.

Requires: asciinema, ffmpeg, playwright (`pip install playwright; playwright install chromium`).

Usage:
    uv run python -m scripts.record-demo --out demo.mp4
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

OUT_DIR = Path("recordings")
SEGMENTS = OUT_DIR / "segments"


def check_tools() -> list[str]:
    """Return missing tools. Empty list = all good."""
    missing: list[str] = []
    for tool in ("asciinema", "ffmpeg"):
        if shutil.which(tool) is None:
            missing.append(tool)
    try:
        import playwright  # noqa: F401
    except ImportError:
        missing.append("playwright (pip install playwright; playwright install chromium)")
    return missing


def record_agent_loop(seconds: int = 30) -> Path:
    out = SEGMENTS / "01-agent-loop.cast"
    print(f"[record] agent loop → {out} ({seconds}s)")
    subprocess.run(
        ["asciinema", "rec", str(out), "--overwrite", "--idle-time-limit", "1.5", "--command",
         f"timeout {seconds} uv run python -m agent.loop"],
        check=False,
    )
    return out


def record_demo_runner(seconds: int = 60, base_url: str = "http://localhost:8000") -> Path:
    out = SEGMENTS / "02-demo-runner.cast"
    print(f"[record] demo runner → {out}")
    subprocess.run(
        ["asciinema", "rec", str(out), "--overwrite", "--idle-time-limit", "1.5", "--command",
         f"uv run python -m scripts.demo-runner --base-url {base_url}"],
        check=False,
    )
    return out


def record_dashboard(
    dashboard_url: str = "http://localhost:3000",
    v3_trace_id: int | None = None,
) -> Path:
    out = SEGMENTS / "03-dashboard.mp4"
    print(f"[record] dashboard → {out}")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[record]  playwright not installed; skipping dashboard segment")
        return out
    # Tour: home (live feed + hero pills) → traces archive → individual v3 trace
    # (ensemble + critic + falsifiables) → calibration → events stream → stats.
    pages: list[str] = ["/", "/traces"]
    if v3_trace_id is not None:
        pages.append(f"/traces/{v3_trace_id}")
    pages.extend(["/calibration", "/events", "/stats"])
    SEGMENTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(SEGMENTS),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        for path in pages:
            page.goto(f"{dashboard_url}{path}")
            page.wait_for_load_state("networkidle")
            # V3 trace pages need a beat for the async Irys fetch to land.
            wait_ms = 6000 if path.startswith("/traces/") else 3500
            page.wait_for_timeout(wait_ms)
            for _ in range(8):
                page.mouse.wheel(0, 240)
                page.wait_for_timeout(180)
        context.close()
        browser.close()
    # Playwright writes a .webm; convert.
    for w in SEGMENTS.glob("*.webm"):
        subprocess.run(["ffmpeg", "-y", "-i", str(w), "-vcodec", "libx264", str(out)], check=False)
        w.unlink(missing_ok=True)
    return out


def stitch(segments: list[Path], out_path: Path) -> None:
    SEGMENTS.mkdir(parents=True, exist_ok=True)
    list_file = SEGMENTS / "concat.txt"
    list_file.write_text(
        "\n".join(f"file '{seg.resolve().as_posix()}'" for seg in segments if seg.exists())
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out_path)],
        check=False,
    )
    print(f"[record] stitched → {out_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record the submission demo.")
    parser.add_argument("--out", default="recordings/demo.mp4")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--dashboard", default="http://localhost:3000")
    parser.add_argument("--skip-loop", action="store_true")
    parser.add_argument("--skip-demo", action="store_true")
    parser.add_argument("--skip-dashboard", action="store_true")
    parser.add_argument(
        "--v3-trace-id",
        type=int,
        default=None,
        help="receipt id of an rr-trace/3 row — visited in the dashboard tour",
    )
    args = parser.parse_args(argv)

    SEGMENTS.mkdir(parents=True, exist_ok=True)

    missing = check_tools()
    if missing:
        print("[record] WARNING — missing tools:", ", ".join(missing))
        print("[record]   missing-tool segments will be skipped.")

    segments: list[Path] = []
    if not args.skip_loop and shutil.which("asciinema"):
        segments.append(record_agent_loop())
    if not args.skip_demo and shutil.which("asciinema"):
        segments.append(record_demo_runner(base_url=args.api))
    if not args.skip_dashboard:
        seg = record_dashboard(dashboard_url=args.dashboard, v3_trace_id=args.v3_trace_id)
        if seg.exists():
            segments.append(seg)

    if not segments:
        print("[record] no segments recorded — aborting.")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stitch(segments, out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
