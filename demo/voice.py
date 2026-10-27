"""Add the narration to the recorded demo: voice, timing, subtitles, MP4.

    python3 voice.py                 # in the folder with demo.webm, scenes.json, narration.json
    VOICE="Zoe (Premium)" python3 voice.py

On a Mac it speaks with the system's own voices (`say`), offline. The best
ones are free downloads: System Settings → Accessibility → Spoken Content →
System voice → Manage Voices… → English → e.g. "Ava (Premium)". Elsewhere it
falls back to espeak-ng, which is only good for checking timing.

Each line starts at the moment its scene really started in the recording
(scenes.json), and is sped up slightly if it would run past its scene. Needs
ffmpeg (on a Mac: brew install ffmpeg).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path.cwd()
LEAD = 0.6            # seconds after a scene starts before its line begins
TAIL = 0.7            # seconds of quiet kept before the next scene
PREFERRED = ["Ava (Premium)", "Zoe (Premium)", "Ava (Enhanced)", "Zoe (Enhanced)",
             "Evan (Enhanced)", "Samantha (Enhanced)", "Samantha"]


def run(*cmd: str) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def duration(path: Path) -> float:
    return float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)))


def pick_voice() -> tuple[str, str]:
    if shutil.which("say"):
        if os.environ.get("VOICE"):
            return "say", os.environ["VOICE"]
        listed = [m.group(1).strip() for m in (re.match(r"^(.+?)\s{2,}[a-z]{2}_[A-Z]{2}", line)
                                                for line in run("say", "-v", "?").splitlines()) if m]
        for name in PREFERRED:
            if name in listed:
                return "say", name
        return "say", next((v for v in listed if v), "Samantha")
    if shutil.which("espeak-ng"):
        return "espeak-ng", os.environ.get("VOICE", "en-us")
    sys.exit("No speech engine: run this on a Mac, or install espeak-ng to check timing.")


def speak(engine: str, voice: str, rate: int, text: str, out: Path) -> None:
    if engine == "say":
        run("say", "-v", voice, "-r", str(rate), "-o", str(out.with_suffix(".aiff")), text)
        run("ffmpeg", "-y", "-loglevel", "error", "-i", str(out.with_suffix(".aiff")), "-ar", "48000", str(out))
    else:
        run("espeak-ng", "-v", voice, "-s", str(rate), "-w", str(out), text)


def cues(text: str, start: float, length: float) -> list[tuple[float, float, str]]:
    """Subtitle cues: the line split into sentences, timed by their share of the words."""
    sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", text) if s.strip()]
    words = [len(s.split()) for s in sentences]
    total, t, out = sum(words), start, []
    for sentence, n in zip(sentences, words, strict=True):
        span = length * n / total
        out.append((t, t + span, sentence))
        t += span
    return out


def stamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def main() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found. On a Mac: brew install ffmpeg")
    lines = {s["id"]: s for s in json.loads((HERE / "narration.json").read_text())["scenes"]}
    timing = json.loads((HERE / "scenes.json").read_text())["scenes"]
    video = HERE / "demo.webm"
    total = duration(video)
    engine, voice = pick_voice()
    print(f"voice: {voice} ({engine})")

    work = Path(tempfile.mkdtemp(prefix="cerebro-voice-"))
    clips, subtitles = [], []
    for i, scene in enumerate(timing):
        line = lines[scene["id"]]
        start = scene["start"] + LEAD
        nxt = timing[i + 1]["start"] if i + 1 < len(timing) else total
        room = max(1.0, nxt - start - TAIL)
        clip, rate = work / f"{i:02}.wav", int(os.environ.get("RATE", "175"))
        speak(engine, voice, rate, line["text"], clip)
        length = duration(clip)
        if length > room:  # a little faster, never past easy listening
            rate = min(215, int(rate * length / room) + 1)
            speak(engine, voice, rate, line["text"], clip)
            length = duration(clip)
        if length > room:
            fitted = work / f"{i:02}-fit.wav"
            run("ffmpeg", "-y", "-loglevel", "error", "-i", str(clip), "-filter:a",
                f"atempo={min(1.25, length / room):.3f}", str(fitted))
            clip, length = fitted, duration(fitted)
        clips.append((clip, start))
        subtitles += cues(line["text"], start, length)
        print(f"  {scene['id']:10} at {start:6.1f}s  {length:5.1f}s of {room:5.1f}s  rate {rate}")

    inputs, chains = [], []
    for n, (clip, start) in enumerate(clips):
        inputs += ["-i", str(clip)]
        ms = int(start * 1000)
        chains.append(f"[{n}]adelay={ms}|{ms}[a{n}]")
    mix = "".join(f"[a{n}]" for n in range(len(clips)))
    narration = work / "narration.wav"
    run("ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex",
        ";".join(chains) + f";{mix}amix=inputs={len(clips)}:normalize=0,apad,atrim=0:{total:.3f},"
        "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[out]",
        "-map", "[out]", "-ac", "2", str(narration))

    srt = HERE / "CEREBRO-demo.srt"
    srt.write_text("\n".join(f"{k}\n{stamp(a)} --> {stamp(b)}\n{text}\n" for k, (a, b, text) in enumerate(subtitles, 1)))
    out = HERE / "CEREBRO-demo.mp4"
    run("ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(narration), "-i", str(srt),
        "-map", "0:v", "-map", "1:a", "-map", "2:s", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "192k", "-c:s", "mov_text",
        "-metadata:s:s:0", "language=eng", "-movflags", "+faststart", str(out))
    shutil.rmtree(work, ignore_errors=True)
    print(f"\nvideo: {out}  ({duration(out):.0f}s)\nsubtitles: {srt}")


if __name__ == "__main__":
    main()
