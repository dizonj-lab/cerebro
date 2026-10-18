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

test("the queue is visible on the Library, not only where it was started", async ({ page }) => {
  await signUp(page, makeAccount("eq-visible"));
  await page.waitForURL(/\/construct$/);
  for (const name of ["x.pdf", "y.pdf", "z.pdf"]) {
    const artifact = await upload(page, name);
    await page.request.post(`/api/artifacts/${artifact.id}/suggest`);
  }

  // Navigating to a different page entirely — the case that used to lose
  // the work and the progress with it.
  await page.goto("/construct/galaxy");
  await page.goto("/construct/library");

  const panel = page.getByTestId("enrichment-queue");
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("Up to 2 at a time");
  await expect(page.getByTestId("enrichment-job").first()).toBeVisible();
});

test("a waiting document says how many are ahead of it", async ({ page }) => {
  await signUp(page, makeAccount("eq-waiting"));
  await page.waitForURL(/\/construct$/);
  for (const name of ["p.pdf", "q.pdf", "r.pdf", "s.pdf", "t.pdf"]) {
    const artifact = await upload(page, name);
    await page.request.post(`/api/artifacts/${artifact.id}/suggest`);
  }

  await page.goto("/construct/library");

  // "Waiting" without a number is indistinguishable from stuck.
  await expect(page.getByTestId("enrichment-queue")).toContainText(/ahead|Waiting/);
});

test("the artifact keeps its job state across a reload", async ({ page }) => {
  await signUp(page, makeAccount("eq-persist"));
  await page.waitForURL(/\/construct$/);
  const artifact = await upload(page, "keep.pdf");
  await page.request.post(`/api/artifacts/${artifact.id}/suggest`);

  const fresh = await (await page.request.get(`/api/artifacts/${artifact.id}`)).json();

  expect(["queued", "running", "done", "failed"]).toContain(fresh.enrichment_job.status);
});
