# Brand assets

| File               | Status                                        |
| ------------------ | --------------------------------------------- |
| `cerebro-mark.svg` | **PLACEHOLDER — awaiting the supplied artwork** |

Replace `cerebro-mark.svg` with the CEREBRO head-and-network mark, cropped to
the mark alone: no wordmark, no tagline, no pillar strip. Those are set in type
by `src/components/brand/Logo.tsx` so they stay crisp at every size, inherit the
ink colour token and remain selectable text for search and screen readers.

Requirements:

- Square viewBox, mark centred, no surrounding padding.
- SVG preferred. If only a raster is available, supply a transparent PNG at
  512×512 or larger and change `MARK_SRC` in `Logo.tsx` to match the extension.
- Keep the filename so no component changes are needed.

The mark is decorative in every usage (`alt=""`, `aria-hidden`): the accessible
name comes from the adjacent `CEREBRO` text, so the two are never announced twice.
