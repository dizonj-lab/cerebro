import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";

/**
 * The Timeline, against real extraction.
 *
 * The documents below state their own dates, which is the only way an event
 * reaches this page: nothing here is seeded into a timeline table.
 */
const MEMO =
  "The Atlas migration project completed its cutover in March 2021. " +
  "Governance approved the data retention policy on 2023-09-12. " +
  "Maria Santos was appointed to lead the platform team in June 2021. " +
  "Q3 2024 is the target for the edge computing rollout. " +
  "A closing sentence with no date at all.\n";

async function openTimeline(page: Page, prefix: string, { seed = true } = {}) {
  await signUp(page, makeAccount(prefix));
  await page.waitForURL(/\/construct$/);

  if (seed) {
    const created = await page.request.post("/api/artifacts", {
      multipart: {
        file: { name: "atlas.txt", mimeType: "text/plain", buffer: Buffer.from(MEMO) },
      },
    });
    const artifact = await created.json();
    await page.request.patch(`/api/artifacts/${artifact.id}`, {
      data: {
        metadata: {
          ...artifact.metadata,
          title: "Atlas Memo",
          topics: ["Migration"],
          people: ["Maria Santos"],
          projects: ["Atlas"],
        },
        approve: true,
      },
    });
  }

  await page.goto("/construct/timeline");
  await expect(page.getByRole("heading", { name: "Timeline", level: 1 })).toBeVisible();
}

test("events come from dates the documents state", async ({ page }) => {
  await openTimeline(page, "tl-events");

  const events = page.getByTestId("timeline-event");
  await expect(events.first()).toBeVisible();
  // The card shows the document's own words and the date at its precision.
  await expect(events.filter({ hasText: "Mar 2021" })).toHaveCount(1);
  await expect(events.filter({ hasText: "Q3 2024" })).toHaveCount(1);
  await expect(page.getByTestId("timeline-summary")).toContainText("deterministic_date_parsing");
});

test("lanes are the library's own confirmed topics", async ({ page }) => {
  await openTimeline(page, "tl-lanes");

  // The fixture confirms the topic "Migration", so that is the lane — the
  // timeline is organised the way this library is.
  await expect(page.getByTestId("lane-Migration")).toBeVisible();
  await expect(page.getByTestId("lane-Migration")).toContainText(/[1-9]\d* event/);
  await expect(page.getByTestId("timeline-summary")).toBeVisible();
});

test("a library with no topics falls back to the named lanes", async ({ page }) => {
  await signUp(page, makeAccount("tl-fallback"));
  await page.waitForURL(/\/construct$/);

  const created = await page.request.post("/api/artifacts", {
    multipart: {
      file: { name: "plain.txt", mimeType: "text/plain", buffer: Buffer.from(MEMO) },
    },
  });
  const artifact = await created.json();
  // Registered with no topic confirmed. Topics are cleared explicitly:
  // deterministic enrichment proposes some on upload, and spreading the
  // suggested metadata would confirm them.
  await page.request.patch(`/api/artifacts/${artifact.id}`, {
    data: { metadata: { ...artifact.metadata, title: "Plain", topics: [] }, approve: true },
  });

  await page.goto("/construct/timeline");
  await expect(page.getByTestId("lane-Governance")).toContainText(/[1-9]\d* event/);
  // Only lanes with something in them are drawn: an empty row is noise.
  const lanes = page.locator('[data-testid^="lane-"]');
  for (const lane of await lanes.all()) {
    await expect(lane).toContainText(/[1-9]\d* event/);
  }
});

test("selecting an event shows its evidence and source", async ({ page }) => {
  await openTimeline(page, "tl-select");

  await page.getByTestId("timeline-event").filter({ hasText: "Governance" }).first().click();
  const panel = page.getByTestId("event-panel");

  await expect(panel).toContainText("Governance");
  // The expression that dated it, and the precision kept.
  await expect(panel).toContainText("2023-09-12");
  await expect(panel).toContainText("day precision");

  await panel.getByRole("button", { name: "Sources" }).click();
  await expect(panel).toContainText("Governance approved");
  await expect(panel.getByRole("link", { name: "Open original" })).toBeVisible();
  await expect(panel.getByRole("link", { name: "Open in Library" })).toBeVisible();
});

test("related events explain what they share", async ({ page }) => {
  await openTimeline(page, "tl-related");

  await page.getByTestId("timeline-event").first().click();
  const panel = page.getByTestId("event-panel");
  await panel.getByRole("button", { name: /^Related/ }).click();

  // Co-occurrence, explained — never an asserted semantic link.
  await expect(panel).toContainText(/Both mention|same document|Both in/);
});

test("zoom and the span presets say what is on screen", async ({ page }) => {
  await openTimeline(page, "tl-zoom");

  // The visible window is stated in words, not as a percentage.
  const span = page.getByTestId("zoom-level");
  await expect(span).toContainText(/year|month/);
  const before = await span.textContent();
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(span).not.toHaveText(before ?? "");

  // The most recent year of the library, not an empty stretch in the middle.
  await page.getByRole("button", { name: "1 y", exact: true }).click();
  await expect(span).toContainText("1 year");
  await expect(page.getByTestId("timeline-event").filter({ hasText: "Q3 2024" })).toBeVisible();
  await page.getByRole("button", { name: "All", exact: true }).click();
  await expect(page.getByTestId("timeline-event").first()).toBeVisible();
});

test("axis labels never run together", async ({ page }) => {
  await openTimeline(page, "tl-axis");

  for (const preset of ["All", "10 y", "1 y"]) {
    await page.getByRole("button", { name: preset, exact: true }).click();
    const boxes = await page
      .getByTestId("timeline-axis")
      .locator("span")
      .evaluateAll((els) => els.map((el) => el.getBoundingClientRect()).map((r) => [r.left, r.right]));
    expect(boxes.length).toBeGreaterThan(1);
    for (let i = 1; i < boxes.length; i++) {
      // Each label ends before the next begins, with room to spare.
      expect(boxes[i][0] - boxes[i - 1][1]).toBeGreaterThan(8);
    }
  }
});

test("the navigator shows density and moves the window", async ({ page }) => {
  await openTimeline(page, "tl-nav");

  const navigator = page.getByTestId("timeline-navigator");
  await expect(navigator).toBeVisible();

  // Zoomed out, the window already covers the whole range and cannot move;
  // zooming in first is what gives it somewhere to go.
  await page.getByRole("button", { name: "Zoom in" }).click();
  await page.getByRole("button", { name: "Zoom in" }).click();
  const window_ = page.getByTestId("navigator-window");
  const before = (await window_.boundingBox())!;

  const track = (await navigator.boundingBox())!;
  await page.mouse.move(track.x + track.width * 0.8, track.y + track.height / 2);
  await page.mouse.down();
  await page.mouse.up();

  const after = (await window_.boundingBox())!;
  expect(Math.round(after.x)).not.toBe(Math.round(before.x));
});

test("filters narrow the lanes and reset restores them", async ({ page }) => {
  await openTimeline(page, "tl-filter");
  const events = page.getByTestId("timeline-event");
  // Counted only once a card exists. Reading the count the moment the page
  // settles raced the first render and recorded zero.
  await expect(events.first()).toBeVisible();
  const before = await events.count();

  // Filtering to the library's own lane keeps everything in it.
  await page.getByLabel("Category").selectOption("Migration");
  await expect(page.getByTestId("timeline-summary")).toBeVisible();
  await expect(events).toHaveCount(before);

  await page.getByRole("button", { name: "Reset" }).click();
  // Not an exact count: Reset also refits the window, and only what is
  // inside it renders, so the comparison that matters is that the filter
  // was lifted rather than that the pixels match.
  await expect(page.getByLabel("Category")).toHaveValue("");
  await expect.poll(() => events.count()).toBeGreaterThan(0);
});

test("an unregistered document places nothing on the timeline", async ({ page }) => {
  await openTimeline(page, "tl-draft", { seed: false });
  await page.request.post("/api/artifacts", {
    multipart: { file: { name: "draft.txt", mimeType: "text/plain", buffer: Buffer.from(MEMO) } },
  });

  await page.reload();

  await expect(page.getByTestId("timeline-empty")).toBeVisible();
  await expect(page.getByTestId("timeline-event")).toHaveCount(0);
});

test("the timeline fills the workspace with the rail collapsed", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openTimeline(page, "tl-layout");

  // Navigation defaults to the rail here, as it does on the Galaxy.
  await expect(page.getByRole("button", { name: "Expand navigation" })).toBeVisible();
  const nav = page.locator("nav[aria-label='Workspace']");
  expect((await nav.boundingBox())!.width).toBeLessThanOrEqual(64);

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  expect(overflow).toBe(false);
});

test("a card says which document it came from", async ({ page }) => {
  await openTimeline(page, "tl-card-title");

  // The confirmed title, on every card. It used to be a sentence lifted out
  // of the middle of the document, so a lane read as unrelated noise.
  const cards = page.getByTestId("timeline-event");
  await expect(cards.first()).toContainText("Atlas Memo");
  await expect(cards.filter({ hasText: "Atlas Memo" })).toHaveCount(await cards.count());
});

test("hovering a card shows the document's dates and where each came from", async ({ page }) => {
  await openTimeline(page, "tl-hover");

  await page.getByTestId("timeline-event").first().hover();

  const card = page.getByTestId("timeline-hover");
  await expect(card).toBeVisible();
  await expect(card).toContainText("Atlas Memo");
  await expect(card).toContainText("atlas.txt");
  // A plain text file asserts no dates of its own, and that is said plainly
  // rather than being filled in with the upload time.
  await expect(card).toContainText("Created");
  await expect(card).toContainText("Modified");
  await expect(card).toContainText("not stated by the document");
  // The one date CEREBRO itself knows.
  await expect(card).toContainText("Registered");
});

test("the overview counts events per period and says so", async ({ page }) => {
  await openTimeline(page, "tl-volume");

  const navigator = page.getByTestId("timeline-navigator");
  // The fixture spans March 2021 to Q3 2024: too few years for yearly bars
  // to show a shape, so there is one bar per month, empty months included.
  await expect(navigator).toContainText("Events per month");
  const counts = await navigator
    .locator("[data-count]")
    .evaluateAll((els) => els.map((el) => Number(el.getAttribute("data-count"))));
  expect(counts).toHaveLength(41);
  expect(counts.reduce((a, b) => a + b, 0)).toBe(4);
  await expect(navigator.getByTestId("period-2021-03")).toHaveAttribute("data-count", "1");
});

test("the timeline drags from anywhere that is not a card", async ({ page }) => {
  await openTimeline(page, "tl-drag");

  const canvas = page.getByTestId("timeline-canvas");
  const lane = page.getByTestId("lane-Migration");
  const before = await page.getByTestId("timeline-event").first().evaluate((el) => el.getBoundingClientRect().x);

  // A press over a lane — most of the surface — used to do nothing.
  const box = (await lane.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.7, box.y + box.height - 4);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.4, box.y + box.height - 4, { steps: 8 });
  await page.mouse.up();

  await expect(canvas).toBeVisible();
  const after = await page.getByTestId("timeline-event").first().evaluate((el) => el.getBoundingClientRect().x);
  expect(Math.abs(after - before)).toBeGreaterThan(4);
});

test.describe("east of Greenwich", () => {
  // Dates were read as local midnight and printed in UTC, which in Singapore
  // is the day before: every year and quarter showed one step early.
  test.use({ timezoneId: "Asia/Singapore" });

  test("a stated date reads as stated", async ({ page }) => {
    await openTimeline(page, "tl-tz");
    const events = page.getByTestId("timeline-event");
    await expect(events.filter({ hasText: "Q3 2024" })).toHaveCount(1);
    await expect(events.filter({ hasText: "Mar 2021" })).toHaveCount(1);
  });
});

test("cited dates are hidden, counted, and shown on request", async ({ page }) => {
  await signUp(page, makeAccount("tl-refs"));
  await page.waitForURL(/\/construct$/);
  const text =
    "The vision pipeline went live in March 2024. " +
    "It builds on the classic account of Marr (1982). " +
    "See example.com/2019/05/edge-detection for a tutorial.\n";
  const created = await page.request.post("/api/artifacts", {
    multipart: { file: { name: "vision.txt", mimeType: "text/plain", buffer: Buffer.from(text) } },
  });
  const artifact = await created.json();
  await page.request.patch(`/api/artifacts/${artifact.id}`, {
    data: { metadata: { ...artifact.metadata, title: "Vision Notes", topics: ["Vision"] }, approve: true },
  });
  await page.goto("/construct/timeline");

  const events = page.getByTestId("timeline-event");
  await expect(events).toHaveCount(1);
  await expect(page.getByTestId("timeline-references")).toHaveText("2 references hidden");
  // The window opens on the document's own events, not on 1982.
  await expect(page.getByTestId("timeline-window")).not.toContainText("1982");

  await page.getByRole("button", { name: "Show", exact: true }).click();
  await expect(events).toHaveCount(3);
  await expect(events.filter({ hasText: "1982 · cited" })).toHaveCount(1);
  await expect(page.getByTestId("timeline-references")).toHaveText("2 references shown");
});

test("a library whose only dates are references says so and offers them", async ({ page }) => {
  await signUp(page, makeAccount("tl-only-refs"));
  await page.waitForURL(/\/construct$/);
  const text = "Edges follow the classic account of Marr (1982). See example.com/2019/05/edges.\n";
  const created = await page.request.post("/api/artifacts", {
    multipart: { file: { name: "refs.txt", mimeType: "text/plain", buffer: Buffer.from(text) } },
  });
  const artifact = await created.json();
  await page.request.patch(`/api/artifacts/${artifact.id}`, {
    data: { metadata: { ...artifact.metadata, title: "Refs", topics: ["Vision"] }, approve: true },
  });
  await page.goto("/construct/timeline");

  const empty = page.getByTestId("timeline-empty");
  await expect(empty).toContainText("Every date in your documents is a reference");
  await empty.getByRole("button", { name: "Show 2 references" }).click();
  await expect(page.getByTestId("timeline-event")).toHaveCount(2);
});

test("the Timeline reopens as it was left", async ({ page }) => {
  await signUp(page, makeAccount("tl-remember"));
  await page.waitForURL(/\/construct$/);
  const text = "The pipeline went live in March 2024. It builds on Marr (1982).\n";
  const created = await page.request.post("/api/artifacts", {
    multipart: { file: { name: "v.txt", mimeType: "text/plain", buffer: Buffer.from(text) } },
  });
  const artifact = await created.json();
  await page.request.patch(`/api/artifacts/${artifact.id}`, {
    data: { metadata: { ...artifact.metadata, title: "V", topics: ["Vision"] }, approve: true },
  });
  await page.goto("/construct/timeline");
  await page.getByRole("button", { name: "Show", exact: true }).click();
  await expect(page.getByTestId("timeline-references")).toContainText("shown");
  await page.getByRole("button", { name: "1 y", exact: true }).click();
  const span = await page.getByTestId("timeline-window").textContent();
  await page.waitForTimeout(500);

  await page.goto("/construct");
  await page.goto("/construct/timeline");
  await expect(page.getByTestId("timeline-references")).toContainText("shown");
  await expect(page.getByTestId("timeline-window")).toHaveText(span ?? "");
});
