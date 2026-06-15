"""narrate-mimo.py — Xiaomi MiMo TTS narration for the Circle grant video.

Generates a single 24kHz mono WAV aligned to the stitched video timeline
(codebase walkthrough + live dashboard tour) plus a matching SRT subtitle
file. MiMo's TTS model is OpenAI-chat-shaped: POST /chat/completions with
model `mimo-v2.5-tts` and the text to speak in an ASSISTANT-role message;
the reply carries base64 WAV in `choices[0].message.audio.data`.

Credentials come from .env (MIMO_API_KEY / MIMO_API_BASE) — never hardcoded.

Output:
  recordings/narration.wav   16-bit PCM, 24kHz mono, ~160s
  recordings/narration.srt   subtitles aligned to the same timeline

Mux happens in a second ffmpeg step (see record-grant-video.sh).
"""

from __future__ import annotations

import base64
import io
import os
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

API_BASE = os.environ.get("MIMO_API_BASE", "https://api.xiaomimimo.com/v1")
API_KEY = os.environ.get("MIMO_API_KEY", "")
TTS_MODEL = "mimo-v2.5-tts"
SAMPLE_RATE = 24000  # MiMo TTS returns 24kHz mono 16-bit


@dataclass(frozen=True)
class Cue:
    """One narration line pinned to an absolute start time on the video."""

    start_s: float
    text: str


# Start times track the stitched video: codewalk panels dwell ~9s each from
# ~1.2s; the dashboard tour begins after the ~64s xfade. Generous spacing so a
# slightly-long clip never collides with the next cue.
CUES: list[Cue] = [
    # --- codebase walkthrough (panels dwell ~9s each; keep each line under ~8.5s) ---
    Cue(1.5, "ReasoningReceipt puts six Circle products into production. "
             "Here is where each one lives in the code."),
    Cue(10.6, "Circle developer-controlled wallets — a portfolio wallet and a consumer "
              "wallet, provisioned headlessly in about four seconds."),
    Cue(19.7, "Every oracle call is paywalled with Circle's x402 version two: a 402 "
              "challenge, an EIP-3009 signature, Gateway settlement."),
    Cue(28.8, "The trace is hashed into a Merkle root on Arc, inside Receipt Registry V2 — "
              "a fraction of a cent in gas."),
    Cue(37.9, "Cross-chain uses CCTP version two: one USDC, Sepolia to Arc, "
              "in about sixty seconds."),
    Cue(46.8, "And App Kit reads the agent's USDC across all twelve testnet chains, "
              "including Arc, as one balance."),
    Cue(56.0, "Six Circle products. One shipped product."),
    # --- live dashboard tour ---
    Cue(66.5, "Now the live product at r-r-trace dot x-y-z. Every probability ships with a "
              "hashed, byte-verifiable trace of the reasoning behind it."),
    Cue(78.0, "Over four thousand five hundred receipts have settled on Arc, across two "
              "hundred twenty-six markets and nineteen consumer wallets. Real on-chain volume."),
    Cue(91.0, "Each receipt is the output of a five-agent ensemble: Bull, Bear and Edge "
              "argue in parallel, a Supervisor merges them, and a Critic audits six rigor "
              "dimensions. Click verify, and the trace is re-hashed client-side."),
    Cue(114.0, "Resolved markets feed a Brier score back into the model's prior. The oracle "
               "calibrates against its own track record."),
    Cue(125.0, "Connect a wallet, sign a Circle x402 payment, and the receipt lands on Arc "
               "under your own address."),
    Cue(139.0, "Every node of the reasoning DAG gets its own hash, with a Merkle root on Arc. "
               "Challenge a single piece of evidence with a two-hundred-byte proof. "
               "Verify — don't trust."),
]

def tts(client: httpx.Client, text: str) -> bytes:
    """Return raw 24kHz 16-bit mono PCM (WAV body stripped) for `text`."""
    resp = client.post(
        f"{API_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "model": TTS_MODEL,
            # TTS rejects a system role — the text to speak must be a lone
            # assistant-role message.
            "messages": [
                {"role": "assistant", "content": text},
            ],
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()["choices"][0]["message"]["audio"]["data"]
    wav_bytes = base64.b64decode(data)
    with wave.open(io.BytesIO(wav_bytes)) as w:
        assert w.getframerate() == SAMPLE_RATE, f"unexpected rate {w.getframerate()}"
        return w.readframes(w.getnframes())


def fmt_srt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def split_cue(text: str, max_chars: int = 84) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    words = text.split()
    mid = len(words) // 2
    return [" ".join(words[:mid]), " ".join(words[mid:])]


def main() -> int:
    if not API_KEY:
        sys.exit("MIMO_API_KEY not set (add it to .env)")

    out_dir = Path("recordings")
    out_dir.mkdir(parents=True, exist_ok=True)

    total_s = max(c.start_s for c in CUES) + 18.0  # tail room for last cue
    master = bytearray(int(total_s * SAMPLE_RATE) * 2)  # 16-bit silence
    srt_rows: list[tuple[float, float, str]] = []

    with httpx.Client() as client:
        for i, cue in enumerate(CUES, 1):
            print(f"[tts] cue {i}/{len(CUES)} @ {cue.start_s:.1f}s ...", flush=True)
            pcm = None
            for attempt in range(3):
                try:
                    pcm = tts(client, cue.text)
                    break
                except Exception as exc:  # noqa: BLE001
                    print(f"[tts]   attempt {attempt + 1} failed: {exc}", flush=True)
            if pcm is None:
                sys.exit(f"TTS failed for cue {i}")

            dur_s = len(pcm) / (SAMPLE_RATE * 2)
            off = int(cue.start_s * SAMPLE_RATE) * 2
            end = off + len(pcm)
            if end > len(master):  # extend if the last clip overruns
                master.extend(b"\x00" * (end - len(master)))
            master[off:end] = pcm
            srt_rows.append((cue.start_s, cue.start_s + dur_s, cue.text))
            print(f"[tts]   {dur_s:.2f}s", flush=True)

    wav_path = out_dir / "narration.wav"
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(master))
    print(f"[tts] wrote {wav_path}  ({len(master) / (SAMPLE_RATE * 2):.1f}s)", flush=True)

    srt_path = out_dir / "narration.srt"
    with srt_path.open("w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(srt_rows, 1):
            # Clamp each cue to end before the next one starts so two subtitle
            # blocks can never render at once (audio is laid out non-overlapping
            # via the cue start times; this guards the visible track too).
            if i < len(srt_rows):
                end = min(end, srt_rows[i][0] - 0.15)
            f.write(f"{i}\n{fmt_srt_ts(start)} --> {fmt_srt_ts(end)}\n")
            f.write("\n".join(split_cue(text)) + "\n\n")
    print(f"[tts] wrote {srt_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
