import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";
import { makePdf } from "./pdf";

/**
 * The CV as a timeline anchor.
 *
 * Against the real pipeline: a real PDF, real extraction, real approval. The
 * properties under test are the ones that would be embarrassing to get wrong
 * — a career duplicated on re-upload, a correction lost, a date invented, or
 * one person's history visible to another.
 */
const CV = [
  "Joselito Dizon",
  "",
  "Experience",
  "Senior Lead Architect | JPMorgan Chase    2021 - Present",
  "Regional Enterprise Architect, MUFG Bank   Mar 2016 - Dec 2021",
  "",
  "Education",
  "MTech Enterprise Business Analytics, NUS   2024 - 2026",
].join("\n");

async function uploadCv(page: Page, text = CV, name = "cv.pdf") {
  return page.request.post("/api/cv", {
    multipart: {
      file: { name, mimeType: "application/pdf", buffer: makePdf([text]) },
    },
  });
}

test("the profile asks for a CV and says what happens to it", async ({ page }) => {
  await signUp(page, makeAccount("cv-ask"));
  await page.waitForURL(/\/construct$/);
  await page.goto("/construct/profile");

  const panel = page.getByTestId("cv-panel");
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("My CV / Resume");
  // Setup is incomplete, not blocked.
  await expect(page.getByTestId("cv-status")).toContainText("Setup incomplete");
  // The disclosure is shown before the picker, not buried after it.
  await expect(panel).toContainText("visible only to you");
  await expect(panel).toContainText("until you approve it");
});

test("the rest of CEREBRO works without a CV", async ({ page }) => {
  await signUp(page, makeAccount("cv-unblocked"));
  await page.waitForURL(/\/construct$/);

  await page.goto("/construct/library");
  await expect(page).toHaveURL(/\/construct\/library$/);
  await page.goto("/construct/timeline");
  await expect(page.getByRole("heading", { name: "Timeline", level: 1 })).toBeVisible();
});

test("a CV is read into entries that wait for approval", async ({ page }) => {
  await signUp(page, makeAccount("cv-read"));
  await page.waitForURL(/\/construct$/);
  await uploadCv(page);
  await page.goto("/construct/profile");

  await expect(page.getByTestId("cv-status")).toContainText("Needs review");
  const anchors = page.getByTestId("cv-anchor");
  const current = anchors.filter({ hasText: "Senior Lead Architect" });
  await expect(current).toHaveCount(1);
  await expect(current).toContainText("JPMorgan Chase");
  // The CV's own line is shown, so a reading can be checked without opening
  // the document. Anchors read earliest first, so this is the 2016 role.
  await expect(anchors.first()).toContainText("MUFG Bank");
  // An open range is "present", and the stored end date stays null.
  await expect(current).toContainText("present");
});

test("the timeline is personalised only after approval", async ({ page }) => {
  await signUp(page, makeAccount("cv-approve"));
  await page.waitForURL(/\/construct$/);
  await uploadCv(page);

  const before = await (await page.request.get("/api/timeline")).json();
  expect(before.anchors).toEqual([]);

  await page.goto("/construct/profile");
  await page.getByTestId("approve-anchors").click();
  await expect(page.getByTestId("cv-status")).toContainText("Timeline personalised");

  const after = await (await page.request.get("/api/timeline")).json();
  expect(after.anchors.length).toBeGreaterThan(0);
});

test("an anchor shows the CV line it came from", async ({ page }) => {
  await signUp(page, makeAccount("cv-evidence"));
  await page.waitForURL(/\/construct$/);
  await uploadCv(page);
  await page.request.post("/api/cv/approve");

  // A document so the timeline renders its lanes too.
  const created = await page.request.post("/api/artifacts", {
    multipart: {
      file: {
        name: "notes.pdf",
        mimeType: "application/pdf",
        buffer: makePdf(["Migration notes. The cutover completed in March 2021."]),
      },
    },
  });
  const artifact = await created.json();
  await page.request.patch(`/api/artifacts/${artifact.id}`, {
    data: { metadata: { ...artifact.metadata, title: "Notes", topics: ["Migration"] }, approve: true },
  });

  await page.goto("/construct/timeline");
  await expect(page.getByTestId("anchor-band")).toBeVisible();
  await page.getByTestId("anchor-period").first().click();

  const details = page.getByTestId("anchor-details");
  await expect(details).toBeVisible();
  await expect(details).toContainText("from your CV");
  await expect(details).toContainText("Architect");
});

test("re-uploading a CV does not duplicate a career", async ({ page }) => {
  await signUp(page, makeAccount("cv-dupe"));
  await page.waitForURL(/\/construct$/);
  await uploadCv(page);
  const first = await (await page.request.get("/api/cv")).json();

  const response = await uploadCv(page, `${CV}\nAnalyst, Acme Corp   2010 - 2014\n`, "cv-v2.pdf");
  const second = await response.json();

  expect(second.extraction.added).toBe(1);
  expect(second.anchors.length).toBe(first.anchors.length + 1);
});

test("one person's CV is invisible to another", async ({ page }) => {
  await signUp(page, makeAccount("cv-owner"));
  await page.waitForURL(/\/construct$/);
  await uploadCv(page);
  await page.request.post("/api/cv/approve");
  await page.request.post("/api/auth/logout");

  await signUp(page, makeAccount("cv-other"));
  await page.waitForURL(/\/construct$/);
  const theirs = await (await page.request.get("/api/cv")).json();

  expect(theirs.anchors).toEqual([]);
  expect(theirs.filename).toBeNull();
  const timeline = await (await page.request.get("/api/timeline")).json();
  expect(timeline.anchors).toEqual([]);
});
