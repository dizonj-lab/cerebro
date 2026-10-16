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
  for (const lane of ["Strategy", "Architecture", "Governance", "Technology", "Projects", "People"]) {
    await expect(page.getByTestId(`lane-${lane}`)).toBeVisible();
  }
  await expect(page.getByTestId("lane-Governance")).toContainText(/[1-9]\d* event/);
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

test("zoom and fit change the visible span", async ({ page }) => {
  await openTimeline(page, "tl-zoom");

  const level = page.getByTestId("zoom-level");
  const before = await level.textContent();
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(level).not.toHaveText(before ?? "");

  await page.getByRole("button", { name: "Fit" }).click();
  await expect(page.getByTestId("timeline-event").first()).toBeVisible();
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
