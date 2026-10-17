import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";
import { makePdf } from "./pdf";

/**
 * The Performance Report, against real measurements.
 *
 * Nothing here is seeded into a metrics table: the numbers come from doing
 * the work — uploading, registering, searching and asking — and reading back
 * what each one cost.
 */
async function work(page: Page) {
  const created = await page.request.post("/api/artifacts", {
    multipart: {
      file: {
        name: "notes.pdf",
        mimeType: "application/pdf",
        buffer: makePdf([
          "Migration notes. The Atlas migration completed its cutover in March 2021.",
          "Further migration detail, with database context.",
        ]),
      },
    },
  });
  const artifact = await created.json();
  await page.request.patch(`/api/artifacts/${artifact.id}`, {
    data: {
      metadata: { ...artifact.metadata, title: "Atlas Notes", topics: ["Migration"] },
      approve: true,
    },
  });
  await page.request.post("/api/search", { data: { query: "migration", mode: "hybrid" } });
  await page.request.post("/api/recall", { data: { question: "zzz unrelated xylophone" } });
}

test("an untouched library says so instead of showing zeroes", async ({ page }) => {
  await signUp(page, makeAccount("perf-empty"));
  await page.waitForURL(/\/construct$/);

  await page.goto("/construct/performance");

  await expect(page.getByRole("heading", { name: "Performance", level: 1 })).toBeVisible();
  await expect(page.getByText(/Nothing measured yet/)).toBeVisible();
});

test("real work is measured and broken down by stage", async ({ page }) => {
  await signUp(page, makeAccount("perf-stages"));
  await page.waitForURL(/\/construct$/);
  await work(page);

  await page.goto("/construct/performance");

  const totals = page.getByTestId("perf-totals");
  await expect(totals).toContainText("Operations");
  // Most of CEREBRO is deterministic, and the report says so rather than
  // implying a model did everything.
  await expect(totals).toContainText("ran without a model");
  await expect(page.getByTestId("perf-latency")).toContainText("ingestion");
  await expect(page.getByTestId("perf-models")).toContainText("deterministic (no model)");
});

test("Ask CEREBRO reports its response cost and counts a refusal apart", async ({ page }) => {
  await signUp(page, makeAccount("perf-recall"));
  await page.waitForURL(/\/construct$/);
  await work(page);

  await page.goto("/construct/performance");

  const recall = page.getByTestId("perf-recall");
  await expect(recall).toContainText("Median response");
  await expect(recall).toContainText("Said it could not find");
  // A refusal is counted, never graded — and the page says that out loud.
  await expect(page.getByText(/A refusal is counted, never graded/)).toBeVisible();
});

test("the raw table lists every measurement and filters by stage", async ({ page }) => {
  await signUp(page, makeAccount("perf-table"));
  await page.waitForURL(/\/construct$/);
  await work(page);

  await page.goto("/construct/performance");

  const table = page.getByTestId("perf-table");
  await expect(table).toBeVisible();
  await expect(table).toContainText("artifact.upload");
  await expect(table).toContainText("reciprocal rank fusion");

  await page.getByRole("button", { name: "search", exact: true }).click();
  await expect(table).toContainText("search.hybrid");
  await expect(table).not.toContainText("artifact.upload");
});

test("accuracy is scored from what review kept, and says so", async ({ page }) => {
  await signUp(page, makeAccount("perf-accuracy"));
  await page.waitForURL(/\/construct$/);
  await work(page);

  await page.goto("/construct/performance");

  const accuracy = page.getByTestId("perf-accuracy");
  await expect(accuracy).toBeVisible();
  await expect(accuracy).toContainText("topics");
  await expect(accuracy).toContainText("Precision");
  await expect(accuracy).toContainText("Recall");
  // The caption refuses to let acceptance be read as correctness.
  await expect(page.getByText(/Suggestions kept at human review/)).toBeVisible();
});

test("one person's measurements are invisible to another", async ({ page }) => {
  await signUp(page, makeAccount("perf-owner"));
  await page.waitForURL(/\/construct$/);
  await work(page);
  await page.request.post("/api/auth/logout");

  await signUp(page, makeAccount("perf-other"));
  await page.waitForURL(/\/construct$/);

  const theirs = await (await page.request.get("/api/performance")).json();
  expect(theirs.totals.operations).toBe(0);
});
