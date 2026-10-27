"""An upbeat, light background track, generated rather than downloaded, so it carries no licence.

    python3 music.py 300 bed.wav        # seconds, output

108 BPM in C major, one chord a bar (C → G → Am → F), built from a soft pad,
a plucky eighth-note arpeggio, a round bassline and gentle drums: kick on the
beat, a soft clap on two and four, closed hi-hats on the off-beats. It opens
with pad and pluck only, brings the drums in after two bars, and fades out.
Mixed to sit under narration. Needs numpy.
"""

from __future__ import annotations

import sys
import wave

import numpy as np

RATE = 44100
BPM = 108
BEAT = 60 / BPM
BAR = 4 * BEAT
CHORDS = [  # MIDI notes: root for the bass, then the chord tones
    (36, [60, 64, 67, 72]),   # C
    (43, [59, 62, 67, 71]),   # G
    (45, [60, 64, 69, 72]),   # Am
    (41, [60, 65, 69, 72]),   # F
]
rng = np.random.default_rng(11)


def hz(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def place(out: np.ndarray, at: float, sound: np.ndarray) -> None:
    s = int(at * RATE)
    if s >= len(out):
        return
    n = min(len(sound), len(out) - s)
    out[s:s + n] += sound[:n]


def env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / RATE
    return np.minimum(1, t / max(attack, 1e-4)) * np.exp(-t * decay)


def pluck(note: float, length: float = 0.45) -> np.ndarray:
    n = int(length * RATE)
    t = np.arange(n) / RATE
    f = hz(note)
    tone = np.sin(2 * np.pi * f * t) + 0.45 * np.sin(4 * np.pi * f * t) + 0.18 * np.sin(6 * np.pi * f * t)
    return tone * env(n, 0.004, 7.5)


def bass(note: float, length: float) -> np.ndarray:
    n = int(length * RATE)
    t = np.arange(n) / RATE
    f = hz(note)
    tone = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t)
    return tone * env(n, 0.01, 2.2) * np.clip((length - t) / 0.05, 0, 1)


def pad_chord(notes: list[int], length: float) -> np.ndarray:
    n = int(length * RATE)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for note in notes:
        for d in (-0.05, 0.05):
            out += np.sin(2 * np.pi * hz(note - 12 + d) * t)
    shape = np.clip(t / 0.3, 0, 1) * np.clip((length - t) / 0.4, 0, 1)
    return out * shape / (len(notes) * 2)


def kick() -> np.ndarray:
    n = int(0.35 * RATE)
    t = np.arange(n) / RATE
    freq = 50 + 90 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(freq) / RATE) * np.exp(-t * 9)


def clap() -> np.ndarray:
    n = int(0.22 * RATE)
    noise = rng.standard_normal(n)
    noise = noise - np.convolve(noise, np.ones(8) / 8, mode="same")  # brighter
    return noise * env(n, 0.002, 22) * 0.5


def hat() -> np.ndarray:
    n = int(0.06 * RATE)
    noise = rng.standard_normal(n)
    noise = noise - np.convolve(noise, np.ones(3) / 3, mode="same")
    return noise * env(n, 0.001, 70) * 0.25


def bed(seconds: float) -> np.ndarray:
    total = int(seconds * RATE)
    pads, plucks, lows, drums = (np.zeros(total) for _ in range(4))
    k, c, h = kick(), clap(), hat()
    bars = int(np.ceil(seconds / BAR))
    for b in range(bars):
        start = b * BAR
        root, notes = CHORDS[b % len(CHORDS)]
        place(pads, start, pad_chord(notes, BAR + 0.15))
        # Arpeggio: up and back down in eighths, accent on the beat.
        pattern = [0, 1, 2, 3, 2, 1, 2, 3]
        for i, p in enumerate(pattern):
            place(plucks, start + i * BEAT / 2, pluck(notes[p] + (12 if i == 3 else 0)) * (1.0 if i % 2 == 0 else 0.7))
        # Bass: root on 1, a fifth pickup on the "and" of 3.
        place(lows, start, bass(root, BEAT * 2.4))
        place(lows, start + 2.5 * BEAT, bass(root + 7, BEAT * 1.4) * 0.8)
        if b >= 2:  # drums join after the intro
            for beat in range(4):
                place(drums, start + beat * BEAT, k * 0.9)
                place(drums, start + (beat + 0.5) * BEAT, h)
                if beat in (1, 3):
                    place(drums, start + beat * BEAT, c)
    mix = 0.55 * pads + 0.30 * plucks + 0.55 * lows + 0.45 * drums
    # A light dotted-eighth echo for space.
    d = int(BEAT * 0.75 * RATE)
    mix[d:] += mix[:-d] * 0.18
    fade_in, fade_out = int(1.5 * RATE), int(4 * RATE)
    mix[:fade_in] *= np.linspace(0, 1, fade_in)
    mix[-fade_out:] *= np.linspace(1, 0, fade_out)
    mix /= np.max(np.abs(mix)) + 1e-9
    # Width: the right channel is a slightly delayed copy.
    shift = int(0.011 * RATE)
    right = np.concatenate([np.zeros(shift), mix[:-shift]])
    return np.stack([mix, 0.92 * right + 0.08 * mix], axis=1) * 0.85


def write(path: str, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    write(sys.argv[2], bed(float(sys.argv[1])))
