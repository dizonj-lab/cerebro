import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";
import { makePdf } from "./pdf";

/**
 * GOD MODE — the floating window.
 *
 * Driven with real pointer events against the real browser, because the
 * whole point of the feature is the gesture.
 */
async function open(page: Page, prefix: string) {
  await signUp(page, makeAccount(prefix));
  await page.waitForURL(/\/construct$/);
  await page.getByTestId("god-mode-launcher").click();
  await expect(page.getByTestId("god-mode")).toBeVisible();
}

async function box(page: Page) {
  return (await page.getByTestId("god-mode").boundingBox())!;
}

async function dragTitle(page: Page, dx: number, dy: number) {
  const title = page.getByTestId("god-mode-title");
  const start = (await title.boundingBox())!;
  // Grab the bar itself, left of its controls.
  const from = { x: start.x + 20, y: start.y + start.height / 2 };
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + dx / 2, from.y + dy / 2, { steps: 5 });
  await page.mouse.move(from.x + dx, from.y + dy, { steps: 5 });
  await page.mouse.up();
}

test("the window drags by its title bar and stays inside the viewport", async ({ page }) => {
  await open(page, "god-drag");
  const before = await box(page);

  await dragTitle(page, 180, 120);
  const after = await box(page);
  expect(Math.round(after.x - before.x)).toBeGreaterThan(150);
  expect(Math.round(after.y - before.y)).toBeGreaterThan(100);

  // Dragged hard at the edge, it stops rather than leaving the screen.
  await dragTitle(page, 5000, 5000);
  const clamped = await box(page);
  const viewport = page.viewportSize()!;
  expect(clamped.x + clamped.width).toBeLessThanOrEqual(viewport.width);
  expect(clamped.y + clamped.height).toBeLessThanOrEqual(viewport.height);
});

test("the window resizes from a corner and refuses to go below its minimum", async ({ page }) => {
  await open(page, "god-resize");
  const before = await box(page);

  const corner = (await page.getByTestId("god-mode-resize-se").boundingBox())!;
  await page.mouse.move(corner.x + corner.width / 2, corner.y + corner.height / 2);
  await page.mouse.down();
  await page.mouse.move(corner.x + 140, corner.y + 90, { steps: 8 });
  await page.mouse.up();

  const grown = await box(page);
  expect(grown.width).toBeGreaterThan(before.width + 100);
  expect(grown.height).toBeGreaterThan(before.height + 50);

  // Dragged far past the minimum, it stops at 320 x 240.
  const again = (await page.getByTestId("god-mode-resize-se").boundingBox())!;
  await page.mouse.move(again.x + again.width / 2, again.y + again.height / 2);
  await page.mouse.down();
  await page.mouse.move(again.x - 2000, again.y - 2000, { steps: 10 });
  await page.mouse.up();

  const floor = await box(page);
  expect(Math.round(floor.width)).toBe(320);
  expect(Math.round(floor.height)).toBe(240);
});

test("title-bar controls work without starting a drag", async ({ page }) => {
  await open(page, "god-controls");
  const before = await box(page);

  // Minimize collapses to a widget, which restores the window.
  await page.getByRole("button", { name: "Minimize" }).click();
  await expect(page.getByTestId("god-mode")).toHaveCount(0);
  await page.getByTestId("god-mode-widget").click();
  await expect(page.getByTestId("god-mode")).toBeVisible();
  // The press on the control moved nothing.
  expect(await box(page)).toEqual(before);

  // Maximize and restore, by button and by double-click.
  await page.getByRole("button", { name: "Maximize" }).click();
  await expect(page.getByTestId("god-mode")).toHaveAttribute("data-mode", "maximized");
  await page.getByTestId("god-mode-title").dblclick({ position: { x: 20, y: 10 } });
  await expect(page.getByTestId("god-mode")).toHaveAttribute("data-mode", "normal");
  await page.getByTestId("god-mode-title").dblclick({ position: { x: 20, y: 10 } });
  await expect(page.getByTestId("god-mode")).toHaveAttribute("data-mode", "maximized");

  await page.getByRole("button", { name: "Restore" }).click();
  await page.getByRole("button", { name: "Close GOD MODE" }).first().click();
  await expect(page.getByTestId("god-mode")).toHaveCount(0);
});

test("opacity is adjustable and never drops below half", async ({ page }) => {
  await open(page, "god-opacity");
  const window_ = page.getByTestId("god-mode");

  // 85% by default: visible, without hiding what it floats over.
  expect(Number(await window_.evaluate((el) => getComputedStyle(el).opacity))).toBeCloseTo(0.85, 2);

  const slider = page.getByLabel("Window opacity");
  await expect(slider).toHaveAttribute("min", "50");
  await expect(slider).toHaveAttribute("max", "100");
  await slider.fill("60");
  expect(Number(await window_.evaluate((el) => getComputedStyle(el).opacity))).toBeCloseTo(0.6, 2);
});

test("the keyboard moves and resizes the window", async ({ page }) => {
  await open(page, "god-keyboard");
  const before = await box(page);

  await page.getByTestId("god-mode-title").focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowDown");
  const moved = await box(page);
  expect(Math.round(moved.x - before.x)).toBe(16);
  expect(Math.round(moved.y - before.y)).toBe(16);

  await page.keyboard.press("Shift+ArrowRight");
  const resized = await box(page);
  expect(Math.round(resized.width - moved.width)).toBe(16);
});

test("GOD MODE survives navigation and remembers where it was put", async ({ page }) => {
  await signUp(page, makeAccount("god-journey"));
  await page.waitForURL(/\/construct$/);

  // A registered document, so the telemetry has something real to report.
  const created = await page.request.post("/api/artifacts", {
    multipart: {
      file: {
        name: "ledger.pdf",
        mimeType: "application/pdf",
        buffer: makePdf(["Quarterly reconciliation notes for the ledger."]),
      },
    },
  });
  const artifact = await created.json();
  await page.request.patch(`/api/artifacts/${artifact.id}`, {
    data: { metadata: { ...artifact.metadata, title: "Ledger", topics: ["Records"] }, approve: true },
  });

  await page.goto("/construct/galaxy");
  await page.getByTestId("god-mode-launcher").click();
  await expect(page.getByTestId("god-mode")).toContainText("Documents");

  await dragTitle(page, 200, 140);
  const corner = (await page.getByTestId("god-mode-resize-se").boundingBox())!;
  await page.mouse.move(corner.x + corner.width / 2, corner.y + corner.height / 2);
  await page.mouse.down();
  await page.mouse.move(corner.x + 120, corner.y + 80, { steps: 6 });
  await page.mouse.up();
  await page.getByLabel("Window opacity").fill("70");

  const placed = await box(page);

  // The acceptance route: Galaxy -> Timeline -> Galaxy.
  await page.goto("/construct");
  await page.goto("/construct/galaxy");

  const restored = await box(page);
  expect(Math.round(restored.x)).toBe(Math.round(placed.x));
  expect(Math.round(restored.y)).toBe(Math.round(placed.y));
  expect(Math.round(restored.width)).toBe(Math.round(placed.width));
  expect(Math.round(restored.height)).toBe(Math.round(placed.height));
  expect(
    Number(await page.getByTestId("god-mode").evaluate((el) => getComputedStyle(el).opacity)),
  ).toBeCloseTo(0.7, 2);

  // And the numbers are the library's own, not a reset placeholder.
  await expect(page.getByTestId("god-mode")).toContainText("ledger.pdf");
  await expect(page.getByTestId("god-mode")).toContainText("no quota configured");
});

test("the window does not swallow interaction with what it floats over", async ({ page }) => {
  await open(page, "god-passthrough");
  // Moved out of the way, the page beneath it still takes clicks: the window
  // is only as large as itself, with no full-screen layer behind it.
  await dragTitle(page, 300, 300);

  await page.getByRole("link", { name: "Library", exact: true }).click();
  await page.waitForURL(/\/construct\/library$/);
  await expect(page.getByTestId("god-mode")).toBeVisible();
});

test("GOD MODE opens from the sidebar as well as the header", async ({ page }) => {
  await signUp(page, makeAccount("god-entries"));
  await page.waitForURL(/\/construct$/);

  const nav = page.locator("nav[aria-label='Workspace']");
  const item = nav.getByRole("button", { name: "GOD MODE", exact: true });

  // It reports a switch, not a destination: the window opens over the page
  // the user is on rather than navigating anywhere.
  await expect(item).toHaveAttribute("aria-pressed", "false");
  await item.click();
  await expect(page.getByTestId("god-mode")).toBeVisible();
  await expect(item).toHaveAttribute("aria-pressed", "true");
  expect(new URL(page.url()).pathname).toBe("/construct");

  // The header entry is the same switch, beside Ingest.
  const header = page.locator("header");
  await expect(header.getByTestId("god-mode-launcher")).toHaveAttribute("aria-pressed", "true");
  await header.getByTestId("god-mode-launcher").click();
  await expect(page.getByTestId("god-mode")).toHaveCount(0);
  await expect(item).toHaveAttribute("aria-pressed", "false");
});

test("GOD MODE names the models and algorithms actually in use", async ({ page }) => {
  await open(page, "god-models");

  const window_ = page.getByTestId("god-mode");
  // The deterministic embedder is labelled as such rather than passed off as
  // a pretrained model. This environment has no Ollama daemon, which is
  // itself reported rather than left blank.
  await expect(window_).toContainText("Embedding");
  await expect(window_).toContainText(/deterministic, not pretrained|nomic|mxbai/);
  await expect(window_).toContainText("exact cosine scan");
  await expect(window_).toContainText("reciprocal rank fusion");
  await expect(window_).toContainText(/Ollama/);
});

test("GOD MODE shows the operations that ran, with their durations", async ({ page }) => {
  await signUp(page, makeAccount("god-ops"));
  await page.waitForURL(/\/construct$/);

  const created = await page.request.post("/api/artifacts", {
    multipart: {
      file: {
        name: "ledger.pdf",
        mimeType: "application/pdf",
        buffer: makePdf(["Quarterly reconciliation notes for the ledger."]),
      },
    },
  });
  const artifact = await created.json();
  await page.request.patch(`/api/artifacts/${artifact.id}`, {
    data: { metadata: { ...artifact.metadata, title: "Ledger" }, approve: true },
  });
  // A retrieval, so there is an operation to report.
  await page.request.post("/api/recall", { data: { question: "reconciliation" } });

  await page.getByTestId("god-mode-launcher").click();
  const operations = page.getByTestId("ml-operations");
  await expect(operations).toContainText("recall.retrieve");
  await expect(operations).toContainText("cosine similarity");
  await expect(operations).toContainText("ms");
});
