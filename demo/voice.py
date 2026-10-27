"""Narration for the demo: speak the lines, then build the finished video.

    python3 voice.py speak     # clips/NN.wav + clips/durations.json, before recording
    python3 voice.py build     # demo.webm + scenes.json + clips → CEREBRO-demo.mp4 and .srt
    python3 voice.py           # both (for a recording made without clips)
    python3 voice.py samples   # one sample line in several Kokoro voices, to choose from

Voices, best first:
  kokoro     Kokoro-82M, an open neural voice that runs locally (used on Buddy, in a container).
             VOICE=af_sarah (default), af_heart, af_bella, am_michael, bf_emma, bm_george …
  say        macOS system voices; the "Premium" ones are free downloads in System Settings →
             Accessibility → Spoken Content → Manage Voices. VOICE="Ava (Premium)".
  espeak-ng  robotic; only for checking timing.
ENGINE=kokoro|say|espeak forces one.

Building is what makes it seamless. The recording waits for real models, so
some scenes hold still longer than their line; those stretches are sped up
(at most 3×) until each scene lasts about as long as its narration, and every
line starts right after the one before. Underneath sits a generated ambient
music bed (music.py) that dips whenever the voice speaks. Needs ffmpeg and
numpy.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path.cwd()
SRC = Path(__file__).resolve().parent
CLIPS = HERE / "clips"
LEAD = 0.35          # a scene's line begins this long after the scene does
TAIL = 0.45          # and the scene runs this long after the line ends
GAP = 0.3            # the least silence between two lines
MAX_SPEEDUP = 3.0
MUSIC_DB = -21       # the bed under the voice, before ducking
MAC_VOICES = ["Ava (Premium)", "Zoe (Premium)", "Ava (Enhanced)", "Zoe (Enhanced)",
              "Evan (Enhanced)", "Samantha (Enhanced)", "Samantha"]


def run(*cmd: str) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def duration(path: Path) -> float:
    return float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)))


def lines() -> list[dict]:
    path = HERE / "narration.json" if (HERE / "narration.json").exists() else SRC / "narration.json"
    return json.loads(path.read_text())["scenes"]


# --- Speaking ----------------------------------------------------------------------------------

def engine() -> str:
    wanted = os.environ.get("ENGINE")
    if wanted:
        return wanted
    try:
        import kokoro  # noqa: F401
        return "kokoro"
    except ImportError:
        pass
    if shutil.which("say"):
        return "say"
    if shutil.which("espeak-ng"):
        return "espeak"
    sys.exit("No voice available: install kokoro, run on a Mac, or install espeak-ng.")


def mac_voice() -> str:
    if os.environ.get("VOICE"):
        return os.environ["VOICE"]
    listed = [m.group(1).strip() for m in (re.match(r"^(.+?)\s{2,}[a-z]{2}_[A-Z]{2}", line)
                                            for line in run("say", "-v", "?").splitlines()) if m]
    return next((v for v in MAC_VOICES if v in listed), "Samantha")


def speak() -> None:
    kind = engine()
    CLIPS.mkdir(exist_ok=True)
    durations = {}
    if kind == "kokoro":
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline

        voice = os.environ.get("VOICE", "af_sarah")
        pipeline = KPipeline(lang_code=voice[0], repo_id="hexgrad/Kokoro-82M")
        speed = float(os.environ.get("SPEED", "0.92"))  # a little slower than default reads warmer
    else:
        voice = mac_voice() if kind == "say" else os.environ.get("VOICE", "en-us")
    print(f"voice: {voice} ({kind})")
    for i, line in enumerate(lines()):
        out = CLIPS / f"{i:02}.wav"
        if kind == "kokoro":
            parts = [np.asarray(audio) for _, _, audio in pipeline(line["text"], voice=voice, speed=speed)]
            sf.write(out.with_suffix(".raw.wav"), np.concatenate(parts), 24000)
            run("ffmpeg", "-y", "-loglevel", "error", "-i", str(out.with_suffix(".raw.wav")), "-ar", "48000", "-ac", "1", str(out))
            out.with_suffix(".raw.wav").unlink()
        elif kind == "say":
            aiff = out.with_suffix(".aiff")
            run("say", "-v", voice, "-r", os.environ.get("RATE", "180"), "-o", str(aiff), line["text"])
            run("ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-ar", "48000", "-ac", "1", str(out))
            aiff.unlink()
        else:
            raw = out.with_suffix(".raw.wav")
            run("espeak-ng", "-v", voice, "-s", os.environ.get("RATE", "165"), "-w", str(raw), line["text"])
            run("ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-ar", "48000", "-ac", "1", str(out))
            raw.unlink()
        durations[line["id"]] = round(duration(out), 2)
        print(f"  {line['id']:10} {durations[line['id']]:5.1f}s")
    (CLIPS / "durations.json").write_text(json.dumps({"voice": voice, "engine": kind, "seconds": durations}, indent=1))
    print(f"total speech {sum(durations.values()):.0f}s")


SAMPLE = ("Every organisation has knowledge scattered across documents. "
          "This is CEREBRO, a private knowledge twin. It reads your documents, connects what they say, "
          "and answers your questions from them.")
SAMPLE_VOICES = ["af_heart", "af_bella", "af_nicole", "af_sarah", "am_michael", "am_fenrir",
                 "am_puck", "bf_emma", "bm_george", "bm_fable"]


def samples() -> None:
    """The same two sentences in several Kokoro voices, to choose from by ear."""
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    out = HERE / "voice-samples"
    out.mkdir(exist_ok=True)
    speed = float(os.environ.get("SPEED", "0.92"))
    pipelines = {}
    for voice in os.environ.get("VOICES", " ".join(SAMPLE_VOICES)).split():
        pipe = pipelines.setdefault(voice[0], KPipeline(lang_code=voice[0], repo_id="hexgrad/Kokoro-82M"))
        audio = np.concatenate([np.asarray(a) for _, _, a in pipe(SAMPLE, voice=voice, speed=speed)])
        wav = out / f"{voice}.wav"
        sf.write(wav, audio, 24000)
        run("ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "128k", str(wav.with_suffix(".mp3")))
        wav.unlink()
        print(f"  {voice}: {wav.with_suffix('.mp3')}")


# --- Building ----------------------------------------------------------------------------------

def stamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def cues(text: str, start: float, length: float) -> list[tuple[float, float, str]]:
    sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", text) if s.strip()]
    words = [len(s.split()) for s in sentences]
    t, out = start, []
    for sentence, n in zip(sentences, words, strict=True):
        span = length * n / sum(words)
        out.append((t, t + span, sentence))
        t += span
    return out


def build() -> None:
    if not (CLIPS / "durations.json").exists():
        speak()
    spoken = json.loads((CLIPS / "durations.json").read_text())["seconds"]
    text = {s["id"]: s["text"] for s in lines()}
    order = [s["id"] for s in lines()]
    video = HERE / "demo.webm"
    timing = json.loads((HERE / "scenes.json").read_text())["scenes"]
    total = duration(video)

    # 1. Each scene's stretch of video, sped up where it holds still too long.
    segments, starts, t = [], [], 0.0
    for i, scene in enumerate(timing):
        a = scene["start"] if i else 0.0
        b = timing[i + 1]["start"] if i + 1 < len(timing) else total
        length = b - a
        want = LEAD + spoken[scene["id"]] + TAIL
        speed = min(MAX_SPEEDUP, length / want) if length > want else 1.0
        segments.append((a, b, speed))
        starts.append(t)
        t += length / speed
    final = t

    # Each stretch rendered on its own and then joined: one filter graph cutting
    # eleven pieces from a 1080p stream buffers enough frames to run out of memory.
    parts = HERE / "parts"
    parts.mkdir(exist_ok=True)
    listing = []
    for k, (a, b, speed) in enumerate(segments):
        part = parts / f"{k:02}.mp4"
        run("ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(video),
            "-vf", f"setpts=(PTS-STARTPTS)/{speed:.4f},fps=30", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(part))
        listing.append(f"file '{part.name}'")
    (parts / "list.txt").write_text("\n".join(listing) + "\n")
    joined = parts / "joined.mp4"
    run("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(parts / "list.txt"),
        "-c", "copy", str(joined))
    filters = []

    # 2. Each line where its scene starts, but never on top of the line before.
    placed, subtitles, cursor = [], [], 0.0
    for k, scene in enumerate(timing):
        sid = scene["id"]
        at = max(starts[k] + LEAD, cursor + GAP)
        placed.append((CLIPS / f"{order.index(sid):02}.wav", at))
        subtitles += cues(text[sid], at, spoken[sid])
        cursor = at + spoken[sid]
        print(f"  {sid:10} scene {starts[k]:6.1f}s  voice {at:6.1f}s  speed ×{segments[k][2]:.2f}")
    final = max(final, cursor + 1.0)

    # 3. Music under it all, ducked by the voice.
    sys.path.insert(0, str(SRC))
    import music

    bed = HERE / "music.wav"
    music.write(str(bed), music.bed(final + 1))

    inputs = ["-i", str(joined), "-i", str(bed)]
    for clip, _ in placed:
        inputs += ["-i", str(clip)]
    voice_chain = []
    for n, (_, at) in enumerate(placed):
        ms = int(at * 1000)
        voice_chain.append(f"[{n + 2}:a]adelay={ms}|{ms},aformat=channel_layouts=stereo[c{n}]")
    filters += voice_chain
    filters.append("".join(f"[c{n}]" for n in range(len(placed))) +
                   f"amix=inputs={len(placed)}:normalize=0,apad,atrim=0:{final:.3f},"
                   "loudnorm=I=-16:TP=-1.5:LRA=11,asplit=2[voice][key]")
    filters.append(f"[1:a]atrim=0:{final:.3f},volume={MUSIC_DB}dB,aformat=channel_layouts=stereo[bed]")
    filters.append("[bed][key]sidechaincompress=threshold=0.02:ratio=6:attack=40:release=600:makeup=1[ducked]")
    filters.append("[voice][ducked]amix=inputs=2:normalize=0,alimiter=limit=0.95[aout]")

    srt = HERE / "CEREBRO-demo.srt"
    srt.write_text("\n".join(f"{k}\n{stamp(a)} --> {stamp(b)}\n{line}\n" for k, (a, b, line) in enumerate(subtitles, 1)))
    out = HERE / "CEREBRO-demo.mp4"
    run("ffmpeg", "-y", "-loglevel", "error", *inputs, "-i", str(srt), "-filter_complex", ";".join(filters),
        "-map", "0:v", "-map", "[aout]", "-map", f"{len(placed) + 2}:s",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng",
        "-t", f"{final:.3f}", "-movflags", "+faststart", str(out))
    bed.unlink()
    shutil.rmtree(parts, ignore_errors=True)
    print(f"\nvideo: {out}  ({duration(out):.0f}s, from {total:.0f}s recorded)\nsubtitles: {srt}")


if __name__ == "__main__":
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found. On a Mac: brew install ffmpeg")
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    if step == "samples":
        samples()
        sys.exit()
    if step in ("speak", "all"):
        speak()
    if step in ("build", "all"):
        build()
