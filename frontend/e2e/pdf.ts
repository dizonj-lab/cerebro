/**
 * A minimal PDF with a real text layer, built by hand.
 *
 * The backend test suite generates its PDFs with reportlab; the browser suite
 * has no PDF library, and the repository does not commit binary fixtures. 650
 * bytes of hand-written PDF is cheaper than either, and it exercises the same
 * extraction path — pypdf reads the text layer out of it exactly as it would
 * from a real document.
 */
export function makePdf(lines: string[]): Buffer {
  const content = Buffer.from(
    `BT /F1 12 Tf 72 720 Td ${lines.map((l) => `(${l}) Tj 0 -16 Td`).join(" ")} ET`,
    "latin1",
  );
  const objects = [
    Buffer.from("<< /Type /Catalog /Pages 2 0 R >>", "latin1"),
    Buffer.from("<< /Type /Pages /Kids [3 0 R] /Count 1 >>", "latin1"),
    Buffer.from(
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] " +
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
      "latin1",
    ),
    Buffer.concat([
      Buffer.from(`<< /Length ${content.length} >>\nstream\n`, "latin1"),
      content,
      Buffer.from("\nendstream", "latin1"),
    ]),
    Buffer.from("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", "latin1"),
  ];

  const parts: Buffer[] = [Buffer.from("%PDF-1.4\n", "latin1")];
  const offsets: number[] = [];
  let length = parts[0].length;
  objects.forEach((object, index) => {
    offsets.push(length);
    const body = Buffer.concat([
      Buffer.from(`${index + 1} 0 obj\n`, "latin1"),
      object,
      Buffer.from("\nendobj\n", "latin1"),
    ]);
    parts.push(body);
    length += body.length;
  });

  const pad = (n: number) => String(n).padStart(10, "0");
  parts.push(
    Buffer.from(
      `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n` +
        offsets.map((o) => `${pad(o)} 00000 n \n`).join("") +
        `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\n` +
        `startxref\n${length}\n%%EOF\n`,
      "latin1",
    ),
  );
  return Buffer.concat(parts);
}
