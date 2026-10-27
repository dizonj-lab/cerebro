/**
 * Where the narrated demo video is published.
 *
 * The video is too large for the repository or the image, so it lives on the
 * portfolio site (folio). The video plays here as plain cross-origin media, so
 * it never depends on CORS; only the small subtitles file is fetched with CORS,
 * and the video plays without it if that fails. `page` is folio's own player,
 * offered if the video cannot load here. Made with demo/run.sh; see demo/README.md.
 */
export const DEMO_VIDEO = {
  src: "https://folio.xtangent.ai/media/cerebro-demo.mp4",
  captions: "https://folio.xtangent.ai/media/cerebro-demo.vtt",
  page: "https://folio.xtangent.ai/demo/cerebro/",
  title: "CEREBRO demo",
} as const;
