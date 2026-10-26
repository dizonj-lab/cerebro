import { expect, test } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";
import { makePdf } from "./pdf";

/** Documents chosen so clusters genuinely share topics, as a real library would. */
const LIBRARY: [string, string[], string[]][] = [
  ["ml_lecture.pdf", ["Machine Learning", "PCA", "Classification"], ["Ada Lovelace"]],
  ["deep_learning.pdf", ["Machine Learning", "Deep Learning"], []],
  ["architecture.pdf", ["Architecture", "Cloud Architecture"], []],
  ["payments.pdf", ["Payments", "Architecture"], []],
  ["career.pdf", ["Career", "Architecture"], []],
];

async function seed(page: import("@playwright/test").Page) {
  for (const [name, topics, people] of LIBRARY) {
    const created = await page.request.post("/api/artifacts", {
      multipart: {
        file: {
          name,
          mimeType: "application/pdf",
          buffer: makePdf([
            `${topics[0]} notes. ${topics[0]} is discussed at length here.`,
            `Further ${topics[0]} detail, with ${topics[1] ?? topics[0]} context.`,
          ]),
        },
      },
    });
    const artifact = await created.json();
    await page.request.patch(`/api/artifacts/${artifact.id}`, {
      data: {
        metadata: { ...artifact.metadata, title: topics[0], topics, people },
        approve: true,
      },
    });
  }
}

async function openGalaxy(page: import("@playwright/test").Page, prefix: string) {
  await signUp(page, makeAccount(prefix));
  await page.waitForURL(/\/construct$/);
  await seed(page);
  await page.goto("/construct/galaxy");
  await expect(page.getByRole("application", { name: "Knowledge Galaxy" })).toBeVisible();
}

test("an empty galaxy invites a first document rather than showing nothing", async ({ page }) => {
  await signUp(page, makeAccount("g-empty"));
  await page.waitForURL(/\/construct$/);
  await page.goto("/construct/galaxy");

  await expect(page.getByRole("heading", { name: "Your Knowledge Galaxy Awaits" })).toBeVisible();
  await page.getByRole("link", { name: /ingest your first document/i }).click();
  await expect(page).toHaveURL(/\/construct\/ingest$/);
});

test("clusters render from registered topics", async ({ page }) => {
  await openGalaxy(page, "g-render");

  for (const label of ["Machine Learning", "Architecture"]) {
    await expect(page.getByRole("button", { name: `${label}, cluster`, exact: true })).toBeVisible();
  }
  // Gradient nodes, not flat circles.
  expect(await page.locator("svg radialGradient").count()).toBeGreaterThan(0);
  expect(await page.locator("svg linearGradient").count()).toBeGreaterThan(0);
});

test("hovering previews a node without any network request", async ({ page }) => {
  await openGalaxy(page, "g-hover");

  const calls: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/")) calls.push(r.url());
  });

  await page.getByRole("button", { name: "Architecture, cluster", exact: true }).hover();
  const tip = page.getByRole("tooltip");
  await expect(tip).toBeVisible();
  await expect(tip).toContainText("Knowledge Cluster");
  await expect(tip).toContainText(/Found in \d+ document/);
  // Hover is a preview: no fetch, and certainly no model call.
  expect(calls).toEqual([]);
});

test("selecting a cluster opens details and dims the unrelated", async ({ page }) => {
  await openGalaxy(page, "g-select");

  await page.getByRole("button", { name: "Architecture, cluster", exact: true }).click();
  const panel = page.getByRole("complementary");
  await expect(panel.getByRole("heading", { name: "Architecture" })).toBeVisible();
  await expect(panel.getByText("Registered & approved")).toBeVisible();

  // Unrelated clusters dim rather than disappear.
  const unrelated = page.getByRole("button", { name: "PCA, cluster", exact: true });
  await expect(unrelated).toHaveAttribute("opacity", "0.25");
});

test("related entries explain the link instead of asserting a relationship", async ({ page }) => {
  await openGalaxy(page, "g-related");

  await page.getByRole("button", { name: "Architecture, cluster", exact: true }).click();
  await page.getByRole("tab", { name: "Related" }).click();
  await expect(page.getByText(/Appears together on \d+ registered document/).first()).toBeVisible();
  await expect(
    page.getByText(/Highly Related|^Related$|Potential Connection/).first(),
  ).toBeVisible();
});

test("documents resolve to the original source", async ({ page }) => {
  await openGalaxy(page, "g-docs");

  await page.getByRole("button", { name: "Machine Learning, cluster", exact: true }).click();
  await page.getByRole("tab", { name: "Documents" }).click();

  const open = page.getByRole("link", { name: "Open original" }).first();
  await expect(open).toBeVisible();
  const response = await page.request.get((await open.getAttribute("href"))!);
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("application/pdf");
});

test("people appear only where a human confirmed them", async ({ page }) => {
  await openGalaxy(page, "g-people");

  await page.getByRole("button", { name: "PCA, cluster", exact: true }).click();
  await page.getByRole("tab", { name: "People" }).click();
  await expect(page.getByText("Ada Lovelace")).toBeVisible();

  await page.getByRole("button", { name: "Payments, cluster", exact: true }).click();
  await page.getByRole("tab", { name: "People" }).click();
  await expect(page.getByText(/none are inferred/)).toBeVisible();
});

test("expanding a cluster loads its fragments on demand", async ({ page }) => {
  await openGalaxy(page, "g-expand");

  const expansions: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/graph/expand")) expansions.push(r.url());
  });

  // Nothing was expanded on load.
  expect(expansions).toEqual([]);
  await page.getByRole("button", { name: "Machine Learning, cluster", exact: true }).click();
  await page.waitForTimeout(500);

  expect(expansions).toHaveLength(1);
  await expect(page.getByRole("button", { name: /, fragment$/ }).first()).toBeVisible();
});

test("a fragment resolves to its page in the source document", async ({ page }) => {
  await openGalaxy(page, "g-fragment");

  await page.getByRole("button", { name: "Machine Learning, cluster", exact: true }).click();
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: /, fragment$/ }).first().click();

  const panel = page.getByRole("complementary");
  await expect(panel.getByText("Source location")).toBeVisible();
  await page.getByRole("tab", { name: "Documents" }).click();
  await expect(panel.getByText(/page \d+/).first()).toBeVisible();
});

test("the timeline renders real events and says where each date came from", async ({ page }) => {
  await openGalaxy(page, "g-timeline");

  await expect(page.getByRole("heading", { name: "Knowledge Timeline" })).toBeVisible();
  // No document states a date, so every event is labelled as registered.
  await expect(page.getByText("· registered").first()).toBeVisible();
  await expect(page.getByText(/Dates stated by the document/)).toBeVisible();
});

test("the timeline shows years, months and how many fall in each", async ({ page }) => {
  await openGalaxy(page, "g-axis");

  const year = String(new Date().getFullYear());
  await expect(page.getByText(year, { exact: true })).toBeVisible();
  // A month tick states its own count rather than leaving a bar to be read.
  const month = page.getByRole("button", { name: /\d+ documents?$/i }).first();
  await expect(month).toBeVisible();

  // Focusing a month narrows the cards without hiding the axis.
  await month.click();
  await expect(page.getByRole("button", { name: "Show all" })).toBeVisible();
});

test("the timeline collapses to give the galaxy the screen", async ({ page }) => {
  await openGalaxy(page, "g-tl-collapse");

  const canvas = page.getByRole("application", { name: "Knowledge Galaxy" });
  const before = (await canvas.boundingBox())!.height;

  await page.getByRole("button", { name: "Hide timeline" }).click();
  await expect(page.getByRole("button", { name: "Show timeline" })).toBeVisible();
  expect((await canvas.boundingBox())!.height).toBeGreaterThan(before);

  await page.getByRole("button", { name: "Show timeline" }).click();
  await expect(page.getByRole("heading", { name: "Knowledge Timeline" })).toBeVisible();
});

test("a timeline card previews the document itself", async ({ page }) => {
  await openGalaxy(page, "g-preview");

  // The preview is the document's own opening, quoted — so it can be checked
  // against the source rather than being a generated blurb.
  await expect(page.getByText(/is discussed at length here/i).first()).toBeVisible();
});

test("timeline and galaxy share one selection", async ({ page }) => {
  await openGalaxy(page, "g-sync");

  // Timeline → Galaxy.
  await page.getByRole("button", { name: /^Architecture,/ }).last().click();
  await expect(
    page.getByRole("complementary").getByRole("heading", { name: "Architecture" }),
  ).toBeVisible();
});

test("the galaxy makes no model call", async ({ page }) => {
  const suspicious: string[] = [];
  page.on("request", (r) => {
    if (/suggest|ollama|11434/.test(r.url())) suspicious.push(r.url());
  });
  await openGalaxy(page, "g-nollm");
  await page.getByRole("button", { name: "Architecture, cluster", exact: true }).click();
  await page.waitForTimeout(500);
  expect(suspicious).toEqual([]);
});

test("the galaxy fits a phone without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await openGalaxy(page, "g-mobile");
  await page.waitForTimeout(400);

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  expect(overflow).toBe(false);
});

// --- browsing, panels, and grounded chat -----------------------------------

test("a node can be dragged to pull a crowded cluster apart", async ({ page }) => {
  await openGalaxy(page, "g-drag");

  const node = page.getByRole("button", { name: "Architecture, cluster", exact: true });
  const before = await node.getAttribute("transform");
  const box = (await node.boundingBox())!;

  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2 + 50, { steps: 8 });
  await page.mouse.up();

  expect(await node.getAttribute("transform")).not.toBe(before);
});

test("the hover dialog reaches the source file", async ({ page }) => {
  await openGalaxy(page, "g-hovercard");

  await page.getByRole("button", { name: "Machine Learning, cluster", exact: true }).click();
  await page.waitForTimeout(600);
  await page.getByRole("button", { name: /, fragment$/ }).first().hover();

  const open = page.getByRole("tooltip").getByRole("link", { name: "Open source" });
  await expect(open).toBeVisible();
  const response = await page.request.get((await open.getAttribute("href"))!);
  expect(response.status()).toBe(200);
});

test("the details panel collapses to an icon and comes back", async ({ page }) => {
  await openGalaxy(page, "g-collapse");
  await page.getByRole("button", { name: "Architecture, cluster", exact: true }).click();
  await expect(page.getByRole("complementary")).toBeVisible();

  await page.getByRole("button", { name: "Collapse details panel" }).click();
  await expect(page.getByRole("complementary").getByRole("tab", { name: "Overview" })).toHaveCount(0);

  await page.getByRole("button", { name: "Expand details panel" }).click();
  await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible();
});

test("the workspace can be maximised and resized", async ({ page }) => {
  await openGalaxy(page, "g-maximise");

  const canvas = page.getByRole("application", { name: "Knowledge Galaxy" });
  const before = (await canvas.boundingBox())!.height;

  const handle = page.getByRole("separator", { name: "Resize timeline" });
  const box = (await handle.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  // Dragging the divider down shrinks the timeline, so the galaxy grows.
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + 120, { steps: 6 });
  await page.mouse.up();
  expect((await canvas.boundingBox())!.height).toBeGreaterThan(before);

  await page.getByRole("button", { name: "Full screen" }).click();
  await expect(page.getByRole("button", { name: "Exit full screen" })).toBeVisible();
});

test("the chat stays shut until asked, then answers from the library", async ({ page }) => {
  await openGalaxy(page, "g-chat");

  const calls: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/recall")) calls.push(r.url());
  });

  await page.getByRole("button", { name: "Architecture, cluster", exact: true }).click();
  await page.waitForTimeout(400);
  // Selecting a node must not call the service.
  expect(calls).toEqual([]);

  await page.getByRole("button", { name: /ask cerebro/i }).click();
  await expect(page.getByText(/Answers come from your registered documents/)).toBeVisible();

  await page.getByLabel("Ask or describe what you're looking for").fill("Architecture notes");
  await page.getByRole("button", { name: "Send" }).click();

  // One request, and the reply cites the document it came from.
  await expect(page.getByRole("link", { name: /Architecture/ }).first()).toBeVisible();
  expect(calls).toHaveLength(1);
});

test("the chat says so rather than inventing an answer", async ({ page }) => {
  await openGalaxy(page, "g-chat-empty");

  await page.getByRole("button", { name: /ask cerebro/i }).click();
  await page.getByLabel("Ask or describe what you're looking for").fill("zzz unrelated xylophone");
  await page.getByRole("button", { name: "Send" }).click();

  // Retrieval found nothing, so no model was asked and nothing was invented.
  await expect(page.getByText(/could not find anything/)).toBeVisible();
});

test("Show me lights the part of the map an answer came from", async ({ page }) => {
  await openGalaxy(page, "g-showme");

  await page.getByRole("button", { name: /Ask CEREBRO/ }).first().click();
  await page.getByLabel("Ask or describe what you're looking for").fill("machine learning");
  await page.getByRole("button", { name: "Send" }).click();

  // The answer arrives with its sources, and offers to map them.
  const showMe = page.getByTestId("show-me").first();
  await expect(showMe).toBeVisible({ timeout: 15000 });
  await showMe.click();

  const map = page.getByTestId("answer-map");
  await expect(map).toBeVisible();
  // It says what was quoted and what was merely found — the distinction
  // retrieval and the citation guard established, not a quality judgement.
  await expect(map).toContainText("quoted");
  await expect(map).toContainText("not part of this answer");

  // Reset returns the galaxy to its unmapped state.
  await page.getByTestId("reset-map").click();
  await expect(map).toHaveCount(0);
});

test("the galaxy turns without relaying itself", async ({ page }) => {
  await openGalaxy(page, "g-rotate");

  const group = page.getByTestId("galaxy-transform");
  await expect(group).toHaveAttribute("data-angle", "0");

  // The control turns the viewpoint. The layout is untouched: a node sits at
  // the same place in the group, which is what keeps every drawn
  // relationship true at any angle.
  const node = page.locator("g[role='button']").first();
  const before = await node.getAttribute("transform");
  await page.getByRole("button", { name: "Rotate clockwise" }).click();

  await expect(group).toHaveAttribute("data-angle", "15");
  await expect(node).not.toHaveAttribute("transform", before ?? "");
  // Labels counter-rotate, so the text stays horizontal.
  expect(await node.getAttribute("transform")).toContain("rotate(-15)");

  // Reset returns the viewpoint, dragging still moves rather than turns.
  await page.getByRole("button", { name: "Reset view" }).click();
  await expect(group).toHaveAttribute("data-angle", "0");
});

test("an edge explains itself and names the documents it rests on", async ({ page }) => {
  await openGalaxy(page, "g-edge");

  // Hovering is forced because an edge drawn as a vertical curve has a
  // zero-width bounding box, which Playwright reads as invisible — a real
  // pointer still hits the 6px stroke, so the check being bypassed is the
  // harness's rather than the browser's.
  //
  // Which edge is hovered is not the point, and depending on the first one
  // made the test depend on layout: a forced hover is dispatched at the
  // element's centre, and for some curves that point is not on the painted
  // stroke. So it tries each in turn and asserts that an edge explains
  // itself — which is the actual claim.
  const edges = page.getByTestId("galaxy-edge");
  const card = page.getByTestId("edge-card");
  const total = await edges.count();
  expect(total).toBeGreaterThan(0);

  // Measured similarity edges are drawn too now, so it looks specifically
  // for a co-occurrence edge — the claim here is about those.
  for (let index = 0; index < total; index += 1) {
    await edges.nth(index).hover({ force: true });
    if ((await card.isVisible()) && (await card.textContent())?.includes("Appears in the same document")) break;
  }

  await expect(card).toBeVisible();
  // What was observed, never what it means: no "uses", no "depends on".
  await expect(card).toContainText("Appears in the same document");
  await expect(card).toContainText("Relationship");
  await expect(card).toContainText("From ");
  // A count of documents, stated as a count.
  await expect(card).toContainText(/\d+ documents?/);
  await expect(card).toContainText("Approved knowledge");
  // A percentage appears only as the measured similarity, under its own name.
  const text = (await card.textContent()) ?? "";
  if (text.includes("%")) expect(text).toContain("Similarity");
});

test("a generic term never becomes a knowledge node", async ({ page }) => {
  await signUp(page, makeAccount("g-generic"));
  await page.waitForURL(/\/construct$/);

  // A document that mentions its own format repeatedly, as documents do.
  const created = await page.request.post("/api/artifacts", {
    multipart: {
      file: {
        name: "formats.pdf",
        mimeType: "application/pdf",
        buffer: makePdf([
          "This PDF explains vector search. The PDF is served over HTTPS.",
          "Vector search ranks results. HTTPS protects the PDF in transit.",
        ]),
      },
    },
  });
  const artifact = await created.json();

  // The suggestions a human is asked to confirm carry the subject, not the
  // format — the filter runs before review, so "PDF" is never offered.
  const suggested = (artifact.metadata.topics ?? []).concat(artifact.metadata.tags ?? []);
  expect(suggested.map((t: string) => t.toLowerCase())).not.toContain("pdf");
  expect(suggested.map((t: string) => t.toLowerCase())).not.toContain("https");
});

/**
 * Measured similarity. These texts are chosen so the hashing embedder the
 * suite runs with finds audio and speech alike, and gardening and accounting
 * like nothing — not even a shared "the".
 */
const ALIKE: [string, string, string][] = [
  ["audio.txt", "Audio", "Speech recognition turns audio signals into text. Spectrogram features of speech audio feed an acoustic model for recognition of spoken words.\n"],
  ["speech.txt", "Speech", "Spoken words are recognised from speech audio. Acoustic models read spectrogram features of speech signals for recognition of spoken text.\n"],
  ["garden.txt", "Gardening", "Tomatoes need compost, sunlight, regular watering. Prune vines, mulch beds early in summer to keep soil moist.\n"],
  ["ledger.txt", "Accounting", "Quarterly invoices reconcile against ledgers; accounts payable closes books once auditors sign balance sheets.\n"],
];

async function openAlike(page: import("@playwright/test").Page, prefix: string) {
  await signUp(page, makeAccount(prefix));
  await page.waitForURL(/\/construct$/);
  for (const [name, topic, text] of ALIKE) {
    const created = await page.request.post("/api/artifacts", {
      multipart: { file: { name, mimeType: "text/plain", buffer: Buffer.from(text) } },
    });
    const artifact = await created.json();
    await page.request.patch(`/api/artifacts/${artifact.id}`, {
      data: { metadata: { ...artifact.metadata, title: name, topics: [topic] }, approve: true },
    });
  }
  await page.goto("/construct/galaxy");
  await expect(page.getByRole("application", { name: "Knowledge Galaxy" })).toBeVisible();
}

test("the legend starts folded, top left, and states this library's own yardstick", async ({ page }) => {
  await openAlike(page, "g-legend");
  const legend = page.getByTestId("galaxy-legend");

  await expect(legend).toBeVisible();
  // Folded by default: the map is what the screen is for.
  await expect(legend).not.toContainText("typical here");
  await legend.getByRole("button", { name: "Reading the Galaxy" }).click();
  const box = (await legend.boundingBox())!;
  const canvas = (await page.getByRole("application", { name: "Knowledge Galaxy" }).boundingBox())!;
  expect(box.x - canvas.x).toBeLessThan(24);
  // The figures are this library's, and the model is named — including that
  // the suite's embedder compares words, not meaning.
  await expect(legend).toContainText(/\d+% is typical here/);
  await expect(legend).toContainText("Measured with hashing");
  await expect(legend).toContainText("shared words, not meaning");
  await expect(legend).toContainText(/Discovered/);

  // It folds away, and comes back.
  await legend.getByRole("button", { name: "Reading the Galaxy" }).click();
  await expect(legend).not.toContainText("typical here");
  await legend.getByRole("button", { name: "Reading the Galaxy" }).click();
  await expect(legend).toContainText("typical here");
});

test("topics that never share a document are linked when alike, with the figure on the line", async ({ page }) => {
  await openAlike(page, "g-discovered");

  const discovered = page.locator('path[data-kind="similar_words"]');
  await expect(discovered.first()).toBeAttached();
  await expect(page.getByTestId("edge-figure").first()).toBeVisible();
  await expect(page.getByTestId("edge-figure").first()).toContainText(/^\d+%$/);
});

test("a passage reaches out to the topic it resembles, or orbits its own", async ({ page }) => {
  await openAlike(page, "g-orbit");
  const legend = page.getByTestId("galaxy-legend");

  await legend.getByRole("button", { name: "Reading the Galaxy" }).click();
  await page.getByRole("button", { name: "Audio, cluster" }).click();
  await expect(legend).toContainText("1 reach out, 0 orbit");
  // Faint or bold by strength, never hidden: the line is there with a strength.
  const reaching = page.locator('path[data-kind="similar_words"][data-strength]');
  await expect(reaching.first()).toBeAttached();

  // Away from Audio first, so its hover card is not over the next topic.
  await page.mouse.move(1, 1);
  await page.getByRole("button", { name: "Gardening, cluster" }).click();
  await expect(legend).toContainText("0 reach out, 1 orbit");
});

test("a similarity line explains its measurement on hover", async ({ page }) => {
  await openAlike(page, "g-measure");
  const card = page.getByTestId("edge-card");

  // Hover a point that is on the curve itself, found from the path's own
  // geometry: the centre of a curve's bounding box is often off the stroke.
  const point = await page
    .locator('path[data-kind="similar_words"] ~ path[data-testid="galaxy-edge"]')
    .first()
    .evaluate((el) => {
      const path = el as SVGPathElement;
      const p = path.getPointAtLength(path.getTotalLength() / 2);
      const m = path.getScreenCTM()!;
      return { x: p.x * m.a + p.y * m.c + m.e, y: p.x * m.b + p.y * m.d + m.f };
    });
  await page.mouse.move(point.x, point.y);

  await expect(card).toContainText("Shares wording");
  await expect(card).toContainText(/Similarity\s*\d+%/);
  await expect(card).toContainText("not a verified link");
  await expect(card).toContainText("hashing");
});

test("what if: an idea is placed among the topics and nothing is stored", async ({ page }) => {
  await openAlike(page, "g-lens");
  const before = await (await page.request.get("/api/artifacts")).json();

  await page.getByLabel("Place an idea in your Galaxy").fill("acoustic speech recognition of spoken audio");
  await page.getByRole("button", { name: "Place", exact: true }).click();
  await expect(page.getByTestId("lens-mark")).toBeAttached();
  expect(await (await page.request.get("/api/artifacts")).json()).toEqual(before);

  // Folded to a tab on the left; hovering the placed idea brings the details out.
  const card = page.getByTestId("lens-card");
  await expect(page.getByTestId("lens-card-tab")).toBeVisible();
  await expect(card).toBeHidden();
  await page.getByTestId("lens-node").hover({ force: true });
  await expect(card).toContainText("closest to");
  await expect(card).toContainText("Audio");
  await expect(card).toContainText("nothing was stored");

  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await expect(page.getByTestId("lens-mark")).toHaveCount(0);
});

test("the what-if window can be kept open, moved, and folded back to the left", async ({ page }) => {
  await openAlike(page, "g-lens-window");
  await page.getByLabel("Place an idea in your Galaxy").fill("speech audio");
  await page.getByRole("button", { name: "Place", exact: true }).click();

  await page.getByTestId("lens-card-tab").click();
  const card = page.getByTestId("lens-card");
  await expect(card).toBeVisible();
  await expect(page.getByTestId("lens-card-tab")).toHaveCount(0);

  const header = card.locator("div").first();
  const before = (await card.boundingBox())!;
  const grip = (await header.boundingBox())!;
  await page.mouse.move(grip.x + 30, grip.y + grip.height / 2);
  await page.mouse.down();
  await page.mouse.move(grip.x + 230, grip.y + 120, { steps: 6 });
  await page.mouse.up();
  const after = (await card.boundingBox())!;
  expect(after.x - before.x).toBeGreaterThan(150);

  await card.getByRole("button", { name: /Minimise the what.if window/ }).click();
  await expect(page.getByTestId("lens-card-tab")).toBeVisible();
});

test("the legend can be moved", async ({ page }) => {
  await openAlike(page, "g-legend-move");
  const legend = page.getByTestId("galaxy-legend");
  const before = (await legend.boundingBox())!;
  await page.mouse.move(before.x + 10, before.y + 15);
  await page.mouse.down();
  await page.mouse.move(before.x + 260, before.y + 180, { steps: 6 });
  await page.mouse.up();
  const after = (await legend.boundingBox())!;
  expect(after.x - before.x).toBeGreaterThan(200);
  expect(after.y - before.y).toBeGreaterThan(130);
});

test("a dragged topic carries its passages with it", async ({ page }) => {
  await openAlike(page, "g-carry");
  const parent = page.getByRole("button", { name: "Gardening, cluster" });
  await parent.click();
  const fragment = page.getByRole("button", { name: /, fragment$/ }).first();
  await expect(fragment).toBeAttached();
  const where = async (el: import("@playwright/test").Locator) => {
    const [, x, y] = ((await el.getAttribute("transform")) ?? "").match(/translate\(([-\d.]+) ([-\d.]+)\)/) ?? [];
    return { x: Number(x), y: Number(y) };
  };
  const p0 = await where(parent);
  const f0 = await where(fragment);

  const box = (await parent.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 120, box.y + box.height / 2 + 60, { steps: 8 });
  await page.mouse.up();

  const p1 = await where(parent);
  const f1 = await where(fragment);
  expect(p1.x - p0.x).toBeGreaterThan(40);
  // The passage moved by exactly as much as its topic did.
  expect(Math.abs(f1.x - f0.x - (p1.x - p0.x))).toBeLessThan(0.5);
  expect(Math.abs(f1.y - f0.y - (p1.y - p0.y))).toBeLessThan(0.5);
});

test("the workspace arrangement is remembered across visits", async ({ page }) => {
  await openGalaxy(page, "g-remember");
  // Hidden, then a reload: it stays hidden. Shown again, it stays shown.
  await page.getByRole("button", { name: "Hide timeline" }).click();
  await page.reload();
  await expect(page.getByRole("button", { name: "Show timeline" })).toBeVisible();
  await page.getByRole("button", { name: "Show timeline" }).click();
  await page.goto("/construct");
  await page.goto("/construct/galaxy");
  await expect(page.getByRole("button", { name: "Hide timeline" })).toBeVisible();
});

test("an opened topic's passages surround it rather than the middle of the map", async ({ page }) => {
  await openAlike(page, "g-around");
  const at = async (name: RegExp) => {
    const transform = (await page.getByRole("button", { name }).first().getAttribute("transform")) ?? "";
    const [, x, y] = transform.match(/translate\(([-\d.]+) ([-\d.]+)\)/) ?? [];
    return { x: Number(x), y: Number(y) };
  };

  for (const topic of ["Gardening", "Audio"]) {
    await page.getByRole("button", { name: `${topic}, cluster` }).click();
    const parent = await at(new RegExp(`^${topic}, cluster$`));
    const fragments = page.getByRole("button", { name: /, fragment$/ });
    await expect(fragments.first()).toBeAttached();
    for (const fragment of await fragments.all()) {
      const transform = (await fragment.getAttribute("transform")) ?? "";
      const [, x, y] = transform.match(/translate\(([-\d.]+) ([-\d.]+)\)/) ?? [];
      // Within the parent's neighbourhood, whether orbiting or leaning out.
      expect(Math.hypot(Number(x) - parent.x, Number(y) - parent.y)).toBeLessThan(110);
    }
  }
});

// --- workspace: header, settings, windows, chat on every page ---------------

test("search sits beside Ingest, and what-if beside Hide timeline", async ({ page }) => {
  await openGalaxy(page, "g-bars");
  // The bordered field, not the text box inside it.
  const search = (await page.getByPlaceholder(/Search your knowledge/).locator("xpath=..").boundingBox())!;
  const ingest = (await page.locator("header").getByRole("link", { name: "Ingest" }).boundingBox())!;
  expect(ingest.x - (search.x + search.width)).toBeGreaterThan(0);
  expect(ingest.x - (search.x + search.width)).toBeLessThan(40);

  const whatIf = (await page.getByLabel("Place an idea in your Galaxy").locator("xpath=ancestor::form").boundingBox())!;
  const hide = (await page.getByRole("button", { name: "Hide timeline" }).boundingBox())!;
  expect(hide.x - (whatIf.x + whatIf.width)).toBeGreaterThan(0);
  expect(hide.x - (whatIf.x + whatIf.width)).toBeLessThan(24);
});

test("Galaxy settings hide the figures and keep the canvas dark, and are remembered", async ({ page }) => {
  await openAlike(page, "g-settings");
  await expect(page.getByTestId("edge-figure").first()).toBeVisible();

  await page.getByRole("button", { name: "Galaxy settings" }).click();
  const panel = page.getByTestId("galaxy-settings");
  await panel.getByLabel(/Similarity figures/).uncheck();
  await expect(page.getByTestId("edge-figure")).toHaveCount(0);
  await expect(panel.getByLabel("Line contrast")).toBeVisible();

  await panel.getByLabel(/Always-dark canvas/).check();
  const frame = page.locator("[data-canvas-frame]");
  await expect(frame).toHaveClass(/scene-dark/);

  await page.reload();
  await expect(page.getByRole("application", { name: "Knowledge Galaxy" })).toBeVisible();
  await expect(page.getByTestId("edge-figure")).toHaveCount(0);
  await expect(page.locator("[data-canvas-frame]")).toHaveClass(/scene-dark/);
});

test("node details open in the floating window and can be pinned", async ({ page }) => {
  await openAlike(page, "g-node-window");
  await page.getByRole("button", { name: "Audio, cluster" }).hover();
  const win = page.getByTestId("node-window");
  await expect(win).toContainText("Knowledge Cluster");

  await win.getByRole("button", { name: "Pin these details" }).click();
  await page.mouse.move(1, 1);
  await expect(win).toContainText("Audio");
  await win.getByRole("button", { name: /Close the details window/ }).click();
  await page.mouse.move(2, 2);
  await expect(win).toHaveCount(0);
});

test("Ask CEREBRO is on every page, movable, and maps an answer onto the Galaxy from elsewhere", async ({ page }) => {
  await openGalaxy(page, "g-chat-anywhere");
  await page.goto("/construct/library");
  await page.getByRole("button", { name: /Ask CEREBRO/ }).click();

  const chat = page.getByTestId("recall-chat");
  await expect(chat).toBeVisible();
  const before = (await chat.boundingBox())!;
  await page.mouse.move(before.x + 120, before.y + 18);
  await page.mouse.down();
  await page.mouse.move(before.x - 200, before.y - 100, { steps: 6 });
  await page.mouse.up();
  const after = (await chat.boundingBox())!;
  expect(before.x - after.x).toBeGreaterThan(150);

  await page.getByLabel("Ask or describe what you're looking for").fill("machine learning");
  await page.getByRole("button", { name: "Send" }).click();
  const showMe = page.getByTestId("show-me").first();
  await expect(showMe).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId("see-timeline").first()).toBeVisible();
  await showMe.click();

  await expect(page).toHaveURL(/\/construct\/galaxy/);
  await expect(page.getByTestId("answer-map")).toBeVisible();
  // Still open, where it was put.
  await expect(chat).toBeVisible();
});
