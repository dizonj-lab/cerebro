# The demo's voice and video assembly: Kokoro (an open neural TTS model, run on
# CPU), espeak-ng (its fallback for unusual words), ffmpeg and numpy.
#   docker build -t cerebro-demo-voice -f demo/voice.Dockerfile demo
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir "kokoro>=0.9.4" "misaki[en]" soundfile numpy \
    && python -m spacy download en_core_web_sm
WORKDIR /work
