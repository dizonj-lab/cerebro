import { expect, test } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";
import { makePdf } from "./pdf";

const BODY =
  "The Atlas migration moves forty database clusters in March. Atlas reporting runs " +
  "in parallel during the migration. Database tests precede the Atlas cutover.";

function textFile(name: string, extra = "") {
  return { name, mimeType: "text/plain", buffer: Buffer.from(`${BODY} ${extra}\n`) };
}

async function openBulk(page: import("@playwright/test").Page, prefix: string) {
  await signUp(page, makeAccount(prefix));
  await page.waitForURL(/\/construct$/);
  await page.goto("/construct/ingest");
  await page.getByRole("button", { name: "Several documents" }).click();
}

test("several documents upload into one table", async ({ page }) => {
  await openBulk(page, "b-upload");

  await page.locator('input[type="file"]').setInputFiles([
    textFile("alpha.txt", "Alpha."),
    textFile("beta.txt", "Beta."),
    { name: "gamma.pdf", mimeType: "application/pdf", buffer: makePdf([BODY, "Gamma page."]) },
  ]);

  await expect(page.getByRole("row")).toHaveCount(4); // header + three files
  await expect(page.getByLabel("Title for alpha.txt")).toBeVisible();
  await expect(page.getByLabel("Topics for gamma.pdf")).toBeVisible();
});

test("a refused file is named without costing the rest", async ({ page }) => {
  await openBulk(page, "b-refused");

  await page.locator('input[type="file"]').setInputFiles([
    textFile("good.txt", "Good."),
    { name: "photo.png", mimeType: "image/png", buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47, 0, 0, 0, 0]) },
  ]);

  await expect(page.getByTestId("refused-files")).toContainText("photo.png");
  await expect(page.getByTestId("refused-files")).toContainText(/cannot read this file type/i);
  // The good file is still there to work with.
  await expect(page.getByLabel("Title for good.txt")).toBeVisible();
});

test("rows arrive prefilled and stay editable until registered", async ({ page }) => {
  await openBulk(page, "b-edit");
  await page.locator('input[type="file"]').setInputFiles([textFile("notes.txt", "Notes.")]);

  const title = page.getByLabel("Title for notes.txt");
  await expect(title).toHaveValue("notes");
  await title.fill("Atlas Migration Notes");
  await expect(title).toHaveValue("Atlas Migration Notes");
});

test("registering the batch makes every row searchable", async ({ page }) => {
  await openBulk(page, "b-register");
  await page.locator('input[type="file"]').setInputFiles([
    textFile("one.txt", "First."),
    textFile("two.txt", "Second."),
  ]);

  await page.getByLabel("Topics for one.txt").fill("Atlas");
  await page.getByLabel("Topics for one.txt").press("Enter");
  await page.getByRole("button", { name: /confirm and register/i }).click();

  await expect(page.getByTestId("row-registered")).toHaveCount(2, { timeout: 15000 });

  // Registration is what builds fragments and vectors: the documents are now
  // findable, which is the proof the pipeline ran.
  const search = await page.request.post("/api/search", {
    data: { query: "Atlas migration database clusters" },
  });
  const body = await search.json();
  expect(body.total).toBeGreaterThan(0);
  expect(body.matches.map((m: { artifact_filename: string }) => m.artifact_filename)).toContain(
    "one.txt",
  );
});

test("an unregistered row stays a draft and out of search", async ({ page }) => {
  await openBulk(page, "b-draft");
  await page.locator('input[type="file"]').setInputFiles([textFile("draft.txt", "Draft only.")]);

  const dashboard = await (await page.request.get("/api/dashboard")).json();
  expect(dashboard.documents.total).toBe(0);
  expect(dashboard.fragments.total).toBe(0);
  // It is still listed as work to do.
  expect(dashboard.recent[0].filename).toBe("draft.txt");
});

test("a single row can be registered on its own", async ({ page }) => {
  await openBulk(page, "b-single-row");
  await page.locator('input[type="file"]').setInputFiles([
    textFile("solo.txt", "Solo."),
    textFile("other.txt", "Other."),
  ]);

  await page.getByRole("button", { name: "Register", exact: true }).first().click();
  await expect(page.getByTestId("row-registered")).toHaveCount(1, { timeout: 15000 });
  // One row left awaiting; "Confirm and register" is a different control.
  await expect(page.getByRole("button", { name: "Register", exact: true })).toHaveCount(1);
});

test("the single-document form still works", async ({ page }) => {
  await signUp(page, makeAccount("b-single"));
  await page.waitForURL(/\/construct$/);
  await page.goto("/construct/ingest");

  await page.locator('input[type="file"]').setInputFiles(textFile("only.txt", "Only one."));
  await expect(page.getByRole("heading", { name: "Review artifact" })).toBeVisible();
});

test("a row can be enriched on its own, and the whole table at once", async ({ page }) => {
  await openBulk(page, "b-enrich");
  await page.locator('input[type="file"]').setInputFiles([
    textFile("one.txt", "First."),
    textFile("two.txt", "Second."),
  ]);

  const calls: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/suggest")) calls.push(r.url());
  });

  // Nothing is asked of the model until the user asks.
  expect(calls).toEqual([]);

  await page.getByRole("button", { name: "Enrich", exact: true }).first().click();
  await expect(page.getByText(/no local model is configured/i).first()).toBeVisible({
    timeout: 15000,
  });
  expect(calls).toHaveLength(1);

  await page.getByRole("button", { name: /enrich all with local ai/i }).click();
  // One request per row, run one at a time rather than in a burst.
  await expect.poll(() => calls.length, { timeout: 20000 }).toBe(3);
});
