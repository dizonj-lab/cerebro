# Brand assets

| File               | Status |
| ------------------ | ------ |
| `cerebro-mark.png` | Supplied artwork, in use |

The head-and-network mark, cropped from the master lockup and centred on a
square transparent canvas at 512×512.

The white background of the master was removed by deriving alpha from each
pixel's distance from white and un-premultiplying the colour, which keeps the
gradients saturated and the edges soft. Verified against white, off-white and
two dark grounds.

The wordmark, tagline and pillar strip are **not** part of this image. They are
set in type by `src/components/brand/Logo.tsx`, so they stay crisp at every
size, inherit the ink colour token, and remain selectable and searchable. That
also lets the header show a compact mark plus wordmark where the full lockup
would be illegible at 64px.

The mark is decorative in every usage (`alt=""`, `aria-hidden`): the accessible
name comes from the adjacent `CEREBRO` text, so the two are never announced
twice.

To replace it, keep the filename and the square canvas — no component changes
are needed. If you supply SVG instead, update `MARK_SRC` in `Logo.tsx`.
