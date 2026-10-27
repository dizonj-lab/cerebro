/**
 * Where the narrated demo video is published.
 *
 * The video is too large for the repository or the image, so it lives on the
 * portfolio site (folio), which serves it with CORS so the subtitles load here
 * too. Made with demo/run.sh; see demo/README.md.
 */
export const DEMO_VIDEO = {
  src: "https://folio.xtangent.ai/media/cerebro-demo.mp4",
  captions: "https://folio.xtangent.ai/media/cerebro-demo.vtt",
  title: "CEREBRO demo",
} as const;
