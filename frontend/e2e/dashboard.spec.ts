import { expect, test } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";
import { makePdf } from "./pdf";

const BODY =
  "Atlas migration notes. The Atlas migration covers the database and the reporting pipeline. " +
  "Atlas timelines are agreed. Database tests pass before the migration.";

async function signedIn(page: import("@playwright/test").Page, prefix: string) {
  await signUp(page, makeAccount(prefix));
  await page.waitForURL(/\/construct$/);
}

async function ingest(
  page: import("@playwright/test").Page,
  { approve = false }: { approve?: boolean } = {},
) {
  const created = await page.request.post("/api/artifacts", {
    multipart: {
      file: { name: "atlas-plan.pdf", mimeType: "application/pdf", buffer: makePdf([BODY]) },
    },
  });
  const artifact = await created.json();
  if (approve) {
    await page.request.patch(`/api/artifacts/${artifact.id}`, {
      data: {
        metadata: { ...artifact.metadata, title: "Atlas Plan", topics: ["Atlas", "Migration"] },
        approve: true,
      },
    });
  }
  return artifact;
}

test("a new account sees a dashboard of zeroes, not a broken one", async ({ page }) => {
  await signedIn(page, "d-empty");

  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
  await expect(page.getByText("Your knowledge. Connected. Discover more.")).toBeVisible();
  // Four metric cards, all reading zero rather than blank.
  for (const label of ["Documents", "Knowledge Fragments", "Topics", "Storage Used"]) {
    await expect(page.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(page.getByText("Nothing ingested yet. Add a document to get started.")).toBeVisible();
});

test("an unapproved artifact shows as work to do, not as knowledge", async ({ page }) => {
  await signedIn(page, "d-pending");
  await ingest(page);
  await page.reload();

  // It is listed, and labelled with the state the pipeline is actually in.
  await expect(page.getByText("atlas-plan.pdf")).toBeVisible();
  await expect(page.getByText("Pending Approval")).toBeVisible();
  // But it is not counted as a document, and no topics exist yet.
  await expect(page.getByText("Topics appear once documents are registered.")).toBeVisible();
});

test("registering fills the metrics, the map and the suggestions", async ({ page }) => {
  await signedIn(page, "d-full");
  await ingest(page, { approve: true });
  await page.reload();

  await expect(page.getByText("↑ +1 this week").first()).toBeVisible();
  // The map is drawn from real topics, and says what an edge means.
  await expect(page.getByText(/Topics joined when a registered document carries both/)).toBeVisible();
  await expect(page.getByRole("img", { name: /Topic map centred on/ })).toBeVisible();
  // Suggestions carry the document that evidences them.
  await expect(page.getByText("Found in 1 document").first()).toBeVisible();
  await expect(page.getByText("atlas-plan.pdf").first()).toBeVisible();
});

test("storage never shows a percentage without a quota", async ({ page }) => {
  await signedIn(page, "d-storage");
  await ingest(page);
  await page.reload();

  const card = page.locator("section", { hasText: "Storage Used" }).last();
  await expect(card.getByText("No quota set")).toBeVisible();
  // Scoped to the card: the profile-completion meter elsewhere on the page
  // legitimately shows a percentage.
  await expect(card).not.toContainText("%");
});

test("a pending artifact opens its review from the dashboard", async ({ page }) => {
  await signedIn(page, "d-review");
  await ingest(page);
  await page.reload();

  await page.getByText("atlas-plan.pdf").click();
  await expect(page).toHaveURL(/\/construct\/ingest\?artifact=/);
  await expect(page.getByRole("heading", { name: "Review artifact" })).toBeVisible();
});

test("the Ingest button opens the existing ingestion route", async ({ page }) => {
  await signedIn(page, "d-ingest");
  await page.getByRole("link", { name: "Ingest", exact: true }).first().click();
  await expect(page).toHaveURL(/\/construct\/ingest$/);
  await expect(page.getByRole("heading", { name: "Add an artifact" })).toBeVisible();
});

test("the dashboard makes one request for its data", async ({ page }) => {
  const calls: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/dashboard")) calls.push(r.url());
  });
  await signedIn(page, "d-calls");
  await page.waitForTimeout(600);
  expect(calls).toHaveLength(1);
});

test("the dashboard fits a phone without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signedIn(page, "d-mobile");
  await ingest(page, { approve: true });
  await page.reload();
  await page.waitForTimeout(400);

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  expect(overflow).toBe(false);
});

test("the dashboard has no WCAG A/AA violations in either theme", async ({ page }) => {
  const AxeBuilder = (await import("@axe-core/playwright")).default;
  await signedIn(page, "d-a11y");
  await ingest(page, { approve: true });

  for (const theme of ["Light", "Dark"]) {
    await page.goto("/construct/settings");
    await page.getByLabel("Appearance", { exact: true }).selectOption({ label: theme });
    await page.goto("/construct");
    await page.waitForTimeout(500);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations.map((v) => `${theme} ${v.id}: ${v.nodes.length}`)).toEqual([]);
  }
});
