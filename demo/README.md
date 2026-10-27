# CEREBRO demo video

A five-minute narrated tour of CEREBRO, recorded on a throwaway instance loaded
with the documents of a fictional company, Larkspur Logistics.

| Step | Where | Command |
|---|---|---|
| Record | Buddy | `cd ~/cerebro && git pull && ./demo/run.sh` |
| Copy | Mac | `scp 'admin@<buddy>:~/cerebro-demo-*.tar.gz' ~/Downloads/` |
| Add the voice | Mac | `tar -xzf cerebro-demo-*.tar.gz && cd cerebro-demo-* && ./voice_mac.sh` |

Result: `CEREBRO-demo.mp4` (1080p, narration, subtitle track) and `CEREBRO-demo.srt`.

## What runs where

- `run.sh` starts the Compose project **cerebro-demo** (`docker-compose.demo.yml`): its own
  database, uploads and Ollama (qwen3, mxbai-embed-large, from the evaluation's model volume),
  on `127.0.0.1:3300`. The live CEREBRO and its data are not touched. `./demo/run.sh down`
  stops it and keeps its data.
- `seed.py` creates `demo@larkspur.example` and registers the 14 documents in
  `corpus/files/library`; the local model reads each one.
- `record.mjs` drives a browser through 11 scenes (`narration.json`) and writes the silent
  video plus `scenes.json`, the moment each scene really started.
- `voice.py` (via `voice_mac.sh`) speaks each line with a macOS voice, starting when its scene
  starts, then muxes video, voice and subtitles. Best voices are free downloads: System Settings →
  Accessibility → Spoken Content → System voice → Manage Voices → English (e.g. "Ava (Premium)").
  Needs `brew install ffmpeg`.

## Changing it

- Words: edit `narration.json`. Keep about 2.3 words per second of each scene's `seconds`.
- Actions: edit the matching `scene(...)` in `record.mjs`.
- Documents: edit `corpus/build.py` and run it (needs python-docx, python-pptx, reportlab, pypdf).
- Dark theme: `THEME=dark ./demo/run.sh record`.

Everything shown is real output from the running models on the made-up library; nothing is
staged. Larkspur Logistics, its people, customers and numbers are invented.
