"""Captions for the demo video from docs/DEMO_SCRIPT.md (phase 11; `make captions`).

Reads the script table (`| # | Time | Visual | Voice-over |`) and writes:
- `submission/captions.srt`: each scene's voice-over split into sentence-sized cues of at most two
  42-character lines, timed from the scene's start at about 150 words a minute;
- `submission/voiceover.txt`: the plain transcript (read it aloud; YouTube Studio's "Auto-sync" can
  time it against the real recording).
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "docs" / "DEMO_SCRIPT.md"
OUT_DIR = ROOT / "submission"
SECONDS_PER_WORD = 60 / 150
LINE = 42


def parse_time(t: str) -> float:
    m, s = t.split(":")
    return int(m) * 60 + int(s)


def srt_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def scenes() -> list[tuple[float, float, str]]:
    rows = []
    for line in SCRIPT.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and re.fullmatch(r"\d+", cells[0]):
            start, end = (parse_time(t) for t in re.split(r"[–-]", cells[1]))
            rows.append((start, end, cells[3]))
    if not rows:
        raise SystemExit(f"no script table found in {SCRIPT}")
    return rows


def cues(text: str) -> list[str]:
    """Sentences, with long ones split at commas/colons so a cue fits two lines."""
    out: list[str] = []
    for sentence in re.split(r"(?<=[.?!])\s+", text):
        if len(sentence) <= 2 * LINE:
            out.append(sentence)
            continue
        part = ""
        for piece in re.split(r"(?<=[,:])\s+", sentence):
            if part and len(part) + 1 + len(piece) > 2 * LINE:
                out.append(part)
                part = piece
            else:
                part = f"{part} {piece}".strip()
        if part:
            out.append(part)
    return out


def main() -> None:
    srt: list[str] = []
    transcript: list[str] = []
    n = 0
    for start, end, text in scenes():
        transcript.append(text)
        parts = cues(text)
        words = [len(p.split()) for p in parts]
        spoken = sum(words) * SECONDS_PER_WORD
        # Speak at ~150 wpm from the scene start; squeeze only if the scene is shorter than that.
        scale = min(1.0, (end - start - 0.4) / spoken) if spoken else 1.0
        t = start + 0.2
        for part, w in zip(parts, words, strict=True):
            duration = max(1.2, w * SECONDS_PER_WORD * scale)
            n += 1
            lines = "\n".join(textwrap.wrap(part, LINE)[:3])
            srt.append(f"{n}\n{srt_time(t)} --> {srt_time(min(t + duration, end))}\n{lines}\n")
            t += duration
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "captions.srt").write_text("\n".join(srt), encoding="utf-8")
    (OUT_DIR / "voiceover.txt").write_text("\n\n".join(transcript) + "\n", encoding="utf-8")
    total = sum(len(t.split()) for t in transcript)
    print(f"✔ submission/captions.srt ({n} cues), submission/voiceover.txt ({total} words)")


if __name__ == "__main__":
    main()
