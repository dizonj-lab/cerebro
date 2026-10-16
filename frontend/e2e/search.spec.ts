import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";
import { makePdf } from "./pdf";

/**
 * Unified search.
 *
 * Seeded through the real API so the fragments, embeddings and full-text
 * index are the ones the application builds. Nothing is stubbed.
 */
const REGISTERED: [string, string, string[]][] = [
  [
    "retention.pdf",
    "Retention Policy",
    ["The retention schedule for ledger exports is seven years.", "Quarterly reconciliation is signed off by the finance lead."],
  ],
  [
    "onboarding.pdf",
    "Onboarding Guide",
    ["New joiners complete the security induction in week one.", "Hardware is issued by the workplace team."],
  ],
];

async function seed(page: Page) {
  for (const [name, title, blocks] of REGISTERED) {
    const created = await page.request.post("/api/artifacts", {
      multipart: { file: { name, mimeType: "application/pdf", buffer: makePdf(blocks) } },
    });
    const artifact = await created.json();
    await page.request.patch(`/api/artifacts/${artifact.id}`, {
      data: {
        metadata: { ...artifact.metadata, title, topics: ["Records"], tags: ["audit"] },
        approve: true,
      },
    });
  }
  // One draft, left unregistered: findable as a document, never as knowledge.
  await page.request.post("/api/artifacts", {
    multipart: {
      file: {
        name: "draft-ledger-notes.pdf",
        mimeType: "application/pdf",
        buffer: makePdf(["Ledger reconciliation draft, not yet reviewed."]),
      },
    },
  });
}

async function openSearch(page: Page, prefix: string, query: string) {
  await signUp(page, makeAccount(prefix));
  await page.waitForURL(/\/construct$/);
  await seed(page);
  await page.goto(`/construct/search?q=${encodeURIComponent(query)}`);
  await expect(page.getByTestId("result-summary")).toBeVisible();
}

test("the header search reaches a results page rather than a dead route", async ({ page }) => {
  await signUp(page, makeAccount("search-header"));
  await page.waitForURL(/\/construct$/);
  await seed(page);

  const box = page.getByRole("combobox", { name: "Search your knowledge" });
  await box.fill("reconciliation");
  await box.press("Enter");

  await page.waitForURL(/\/construct\/search\?q=reconciliation/);
  await expect(page.getByTestId("knowledge-result").first()).toBeVisible();
});

test("the keyboard shortcut focuses the search box", async ({ page }) => {
  await signUp(page, makeAccount("search-shortcut"));
  await page.waitForURL(/\/construct$/);

  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByRole("combobox", { name: "Search your knowledge" })).toBeFocused();

  // Escape gives the page back rather than leaving an open panel.
  await page.keyboard.press("Escape");
  await expect(page.getByRole("combobox", { name: "Search your knowledge" })).not.toBeFocused();
});

test("suggestions complete the user's own metadata", async ({ page }) => {
  await signUp(page, makeAccount("search-suggest"));
  await page.waitForURL(/\/construct$/);
  await seed(page);

  await page.getByRole("combobox", { name: "Search your knowledge" }).fill("reten");
  await expect(page.getByTestId("search-suggestions")).toContainText("Retention Policy");
});

test("a result shows the matched passage and where it came from", async ({ page }) => {
  await openSearch(page, "search-passage", "reconciliation");

  const first = page.getByTestId("knowledge-result").first();
  await expect(first).toContainText("reconciliation");
  await expect(first).toContainText("retention.pdf");
  // Relevance is words, never a percentage.
  await expect(first).toContainText(/Highly Related|Related|Potential Connection/);
  await expect(first).not.toContainText("%");
  await expect(first.getByRole("link", { name: "Open source" })).toBeVisible();
});

test("keyword mode needs no model and still finds an exact term", async ({ page }) => {
  await openSearch(page, "search-keyword", "induction");

  await page.getByRole("button", { name: "Keyword", exact: true }).click();
  await expect(page.getByTestId("result-summary")).toContainText("keyword");
  await expect(page.getByTestId("knowledge-result").first()).toContainText("induction");
});

test("an unregistered document is findable but never presented as knowledge", async ({ page }) => {
  await openSearch(page, "search-draft", "draft ledger notes");

  const draft = page.getByTestId("document-result").filter({ hasText: "draft-ledger-notes" });
  await expect(draft).toBeVisible();
  await expect(draft.getByTestId("not-knowledge")).toContainText("not part of your knowledge yet");
});

test("a filter narrows the results and can be cleared", async ({ page }) => {
  await openSearch(page, "search-filter", "reconciliation");
  const before = await page.getByTestId("knowledge-result").count();
  expect(before).toBeGreaterThan(0);

  await page.getByLabel("Filter by tag").fill("nonexistent-tag");
  await expect(page.getByTestId("no-results")).toBeVisible();

  await page.getByRole("button", { name: /^Clear \(/ }).click();
  await expect(page.getByTestId("knowledge-result").first()).toBeVisible();
});

test("scope limits which groups are searched", async ({ page }) => {
  await openSearch(page, "search-scope", "retention");

  await page.getByLabel("Documents", { exact: true }).check();
  await expect(page.getByTestId("document-result").first()).toBeVisible();
  await expect(page.getByTestId("knowledge-result")).toHaveCount(0);
});

test("Assisted Recollection is present and sends nothing until asked", async ({ page }) => {
  let calls = 0;
  await page.route("**/api/recall", async (route) => {
    calls += 1;
    await route.continue();
  });

  await openSearch(page, "search-recall", "reconciliation");
  await expect(page.getByTestId("recollection-panel")).toBeVisible();
  expect(calls).toBe(0);

  await page.getByLabel("Ask about your knowledge").fill("What is the retention schedule?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByTestId("recollection-answer")).toBeVisible();
  expect(calls).toBe(1);
  // Every answer cites the documents it came from, each a link to the
  // stored original.
  const cited = page.getByTestId("recollection-answer").getByRole("link", {
    name: "Retention Policy",
  });
  await expect(cited.first()).toBeVisible();
});

test("a query with no match explains what to try instead", async ({ page }) => {
  await openSearch(page, "search-empty", "velociraptor husbandry");
  await expect(page.getByTestId("no-results")).toContainText("Nothing in your library matches");
});

test("the search page fits a phone without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openSearch(page, "search-phone", "reconciliation");

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  expect(overflow).toBe(false);
});
