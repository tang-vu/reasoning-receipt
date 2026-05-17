"""generate-demo-narration.py — Gemini 3.1 Flash TTS narration for the demo video.

Calls Vertex AI's `gemini-3.1-flash-tts-preview` once per page-section, pads
each segment with leading/trailing silence so the audio aligns with the
1:21 Playwright dashboard tour, and writes:

  - recordings/demo-audio.wav   (16-bit PCM, 24kHz mono, ~81s)
  - recordings/demo.srt         (subtitles aligned to the audio)

The mux into the final video (audio overlay + burned-in subs) happens in a
second step once ffmpeg is on PATH.

Voice: Charon (male, technical-authority delivery).
"""

from __future__ import annotations

import os
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Each segment maps 1:1 to a page in the Playwright tour. `target_s` is the
# slot the audio is padded into so the narration tracks the on-screen page
# change. Sum of target_s ~= video duration (81s).
@dataclass(frozen=True)
class Segment:
    label: str
    target_s: float
    text: str


SEGMENTS: list[Segment] = [
    Segment(
        label="home",
        target_s=10.0,
        text=(
            "ReasoningReceipt is an on-chain oracle for prediction markets. "
            "Every probability ships with a hashed, byte-verifiable trace "
            "of the reasoning behind it."
        ),
    ),
    Segment(
        label="traces",
        target_s=11.0,
        text=(
            "Forty five hundred receipts settled on Arc Testnet so far. "
            "Two hundred fifteen distinct markets. Seventeen consumer wallets. "
            "Real volume, not synthetic ticks."
        ),
    ),
    Segment(
        label="trace-detail",
        target_s=17.0,
        text=(
            "Each receipt is the output of a five-agent ensemble. "
            "Bull, Bear, and Edge run in parallel. "
            "A Supervisor weighs them with weighted Bayesian synthesis. "
            "A Critic audits six rigor dimensions. "
            "Click verify, and the dashboard re-canonicalises and re-hashes "
            "the trace client-side."
        ),
    ),
    Segment(
        label="calibration",
        target_s=9.0,
        text=(
            "Resolved markets back-feed a per-category Brier score into "
            "the Supervisor's prompt. The oracle calibrates itself "
            "against its own track record."
        ),
    ),
    Segment(
        label="try-live",
        target_s=12.0,
        text=(
            "Connect a wallet. Sign a Circle x402 payment. "
            "The receipt lands on Arc under your address in under a second, "
            "for six hundred and eighty microcents of gas."
        ),
    ),
    Segment(
        label="inclusion",
        target_s=22.0,
        text=(
            "The structural wedge: every node of the reasoning DAG "
            "gets its own SHA-256. A Merkle root over all of them lands "
            "on Arc inside the receipt. Challenge a single piece of evidence "
            "with a two hundred byte inclusion proof. You don't have to trust "
            "the publisher. You verify the part you care about. "
            "Live at rrtrace dot xyz."
        ),
    ),
]

VOICE = "Charon"  # male, deeper, technical-authority feel
STYLE_PROMPT = (
    "Read the following as a calm, technically-confident product narrator. "
    "Slight pauses between sentences. No exaggeration."
)


def tts(client, text: str) -> bytes:
    """Return raw 24kHz 16-bit mono PCM bytes from Gemini Flash TTS."""
    from google.genai import types

    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE)
            )
        ),
    )
    prompt = f"{STYLE_PROMPT}\n\n{text}"
    resp = client.models.generate_content(
        model="gemini-3.1-flash-tts-preview",
        contents=prompt,
        config=config,
    )
    for cand in resp.candidates or []:
        for part in (cand.content.parts if cand.content else []) or []:
            inline = getattr(part, "inline_data", None)
            if inline and inline.data:
                return inline.data
    raise RuntimeError("TTS returned no audio")


def pcm_silence(samples: int) -> bytes:
    """16-bit signed silence, `samples` frames at 24kHz mono."""
    return b"\x00\x00" * samples


def fmt_srt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def write_wav(path: Path, pcm: bytes, sample_rate: int = 24000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)


def split_srt_cue(text: str, max_chars: int = 80) -> list[str]:
    """Split a long sentence into two roughly-balanced subtitle lines."""
    if len(text) <= max_chars:
        return [text]
    words = text.split()
    mid = len(words) // 2
    return [" ".join(words[:mid]), " ".join(words[mid:])]


def main() -> int:
    from google import genai

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        sys.exit("GOOGLE_CLOUD_PROJECT not set")

    # Try global first (matches existing text models), fall back to us-central1.
    last_exc: Exception | None = None
    client = None
    for location in ("global", "us-central1"):
        try:
            client = genai.Client(vertexai=True, project=project, location=location)
            # Quick probe: list models is cheaper than a TTS call.
            _ = client.models.generate_content
            print(f"[tts] using project={project} location={location}", flush=True)
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    if client is None:
        sys.exit(f"could not init genai client: {last_exc}")

    out_dir = Path("recordings")
    out_dir.mkdir(parents=True, exist_ok=True)
    seg_dir = out_dir / "segments-audio"
    seg_dir.mkdir(parents=True, exist_ok=True)

    sample_rate = 24000
    full_pcm = bytearray()
    srt_cues: list[tuple[float, float, str]] = []
    cursor_s = 0.0

    for seg in SEGMENTS:
        print(f"[tts] {seg.label}  ({seg.target_s:.1f}s target)  ...", flush=True)
        # Retry on transient errors.
        pcm = None
        for attempt in range(3):
            try:
                pcm = tts(client, seg.text)
                break
            except Exception as exc:  # noqa: BLE001
                print(f"[tts]   attempt {attempt + 1} failed: {exc}", flush=True)
        if pcm is None:
            sys.exit(f"TTS failed for segment {seg.label}")

        # Cache the raw segment for inspection.
        write_wav(seg_dir / f"{seg.label}.wav", pcm, sample_rate)

        # Duration of the raw audio (samples / rate).
        audio_s = len(pcm) / (sample_rate * 2)
        print(f"[tts]   got {audio_s:.2f}s of audio", flush=True)

        # If shorter than the slot, pad with trailing silence.
        # If longer, accept it (slight overlap) but warn.
        slot_s = seg.target_s
        if audio_s > slot_s + 0.5:
            print(f"[tts]   WARNING: segment runs {audio_s - slot_s:.1f}s long", flush=True)

        # SRT cue starts at cursor, ends when audio ends.
        srt_cues.append((cursor_s, cursor_s + audio_s, seg.text))

        full_pcm.extend(pcm)

        # Pad remainder of the slot with silence so the next segment aligns
        # with the next page transition.
        pad_s = max(0.0, slot_s - audio_s)
        if pad_s > 0:
            full_pcm.extend(pcm_silence(int(pad_s * sample_rate)))

        cursor_s += max(slot_s, audio_s)

    # Final audio
    audio_path = out_dir / "demo-audio.wav"
    write_wav(audio_path, bytes(full_pcm), sample_rate)
    final_s = len(full_pcm) / (sample_rate * 2)
    print(f"[tts] wrote {audio_path}  ({final_s:.1f}s, {audio_path.stat().st_size / 1_000_000:.1f} MB)", flush=True)

    # SRT
    srt_path = out_dir / "demo.srt"
    with srt_path.open("w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(srt_cues, 1):
            lines = split_srt_cue(text)
            f.write(f"{i}\n{fmt_srt_ts(start)} --> {fmt_srt_ts(end)}\n")
            f.write("\n".join(lines) + "\n\n")
    print(f"[tts] wrote {srt_path}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
