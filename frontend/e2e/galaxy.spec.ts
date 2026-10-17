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
