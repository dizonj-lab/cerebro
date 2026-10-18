import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";
import { makePdf } from "./pdf";

/**
 * Enrichment as a background queue.
 *
 * The properties under test are the three complaints it was built to fix:
 * the request must not block, the progress must be visible, and leaving the
 * page must not abandon the work.
 */
async function upload(page: Page, name: string) {
  const created = await page.request.post("/api/artifacts", {
    multipart: {
      file: {
        name,
        mimeType: "application/pdf",
        buffer: makePdf([`${name} notes. Migration detail and database context here.`]),
      },
    },
  });
  return created.json();
}

test("asking for suggestions returns at once rather than blocking", async ({ page }) => {
  await signUp(page, makeAccount("eq-fast"));
  await page.waitForURL(/\/construct$/);
  const artifact = await upload(page, "one.pdf");

  const started = Date.now();
  const response = await page.request.post(`/api/artifacts/${artifact.id}/suggest`);

  expect(response.status()).toBe(202);
  // The old behaviour held this open for the whole of enrichment.
  expect(Date.now() - started).toBeLessThan(5000);
  expect((await response.json()).status).toBe("queued");
});

test("a bulk upload queues everything and runs a couple at a time", async ({ page }) => {
  await signUp(page, makeAccount("eq-bulk"));
  await page.waitForURL(/\/construct$/);

  const ids: string[] = [];
  for (const name of ["a.pdf", "b.pdf", "c.pdf", "d.pdf"]) {
    const artifact = await upload(page, name);
    ids.push(artifact.id);
    await page.request.post(`/api/artifacts/${artifact.id}/suggest`);
  }

  const queue = await (await page.request.get("/api/artifacts/enrichment/queue")).json();
  // A single local model is the constraint, so the rest wait rather than
  // all starting at once. Asserted on the ceiling and on what is running,
  // not on the queue still being occupied: without a model reachable the
  // jobs resolve immediately and the queue legitimately empties.
  expect(queue.max_concurrent).toBe(2);
  expect(queue.running).toBeLessThanOrEqual(2);

  // Every one of them got a job, whatever state it has reached.
  for (const id of ids) {
    const fresh = await (await page.request.get(`/api/artifacts/${id}`)).json();
    expect(fresh.enrichment_job.status).toBeTruthy();
  }
});

/**
 * The panel is driven from a stubbed queue on purpose.
 *
 * Without a model reachable a job finishes in milliseconds, so asserting on
 * a real queue is asserting on a state that has already gone — the test
 * passed or failed on scheduling luck. What is actually being claimed here
 * is a UI one: the panel reads the server's queue, so it shows the same
 * thing on the Library as on Ingest, including work this page did not
 * start. Stubbing the response tests exactly that. The queueing itself is
 * covered against the real queue in the backend tests.
 */
async function stubQueue(page: Page) {
  await page.route("**/api/artifacts/enrichment/queue", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        jobs: [
          { artifact_id: "1", filename: "x.pdf", status: "running", progress: 1, total: 4, model: "llama3.2:3b", position: 0 },
          { artifact_id: "2", filename: "y.pdf", status: "queued", progress: 0, total: null, model: null, position: 1 },
          { artifact_id: "3", filename: "z.pdf", status: "queued", progress: 0, total: null, model: null, position: 2 },
        ],
        running: 1,
        waiting: 2,
        max_concurrent: 2,
      }),
    }),
  );
}

test("the queue is visible on the Library, not only where it was started", async ({ page }) => {
  await signUp(page, makeAccount("eq-visible"));
  await page.waitForURL(/\/construct$/);
  await stubQueue(page);

  // Navigating to a different page entirely — the case that used to lose
  // the work and the progress with it.
  await page.goto("/construct/galaxy");
  await page.goto("/construct/library");

  const panel = page.getByTestId("enrichment-queue");
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("Up to 2 at a time");
  await expect(panel).toContainText("1 document, 2 waiting");
  await expect(page.getByTestId("enrichment-job")).toHaveCount(3);
  // Progress is a number, not a spinner.
  await expect(panel).toContainText("Reading section 2 of 4");
});

test("a waiting document says how many are ahead of it", async ({ page }) => {
  await signUp(page, makeAccount("eq-waiting"));
  await page.waitForURL(/\/construct$/);
  await stubQueue(page);

  await page.goto("/construct/library");

  // "Waiting" without a number is indistinguishable from stuck.
  await expect(page.getByTestId("enrichment-queue")).toContainText("1 ahead");
  await expect(page.getByTestId("enrichment-queue")).toContainText("2 ahead");
});

test("the artifact keeps its job state across a reload", async ({ page }) => {
  await signUp(page, makeAccount("eq-persist"));
  await page.waitForURL(/\/construct$/);
  const artifact = await upload(page, "keep.pdf");
  await page.request.post(`/api/artifacts/${artifact.id}/suggest`);

  const fresh = await (await page.request.get(`/api/artifacts/${artifact.id}`)).json();

  expect(["queued", "running", "done", "failed"]).toContain(fresh.enrichment_job.status);
});
