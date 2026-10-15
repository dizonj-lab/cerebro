import { expect, test } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";

test.beforeEach(async ({ page }) => {
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    if (/Failed to load resource/i.test(msg.text())) return;
    throw new Error(`Console error: ${msg.text()}`);
  });
});

const SAMPLE = "CEREBRO is a Digital Knowledge Twin.\nIt preserves provenance to source artifacts.\n";

async function signedIn(page: import("@playwright/test").Page, prefix: string) {
  const account = makeAccount(prefix);
  await signUp(page, account);
  await page.waitForURL(/\/construct$/);
  return account;
}

async function upload(page: import("@playwright/test").Page, name = "benchmark_001.txt") {
  await page.goto("/construct/ingest");
  await page.locator('input[type="file"]').setInputFiles({
    name, mimeType: "text/plain", buffer: Buffer.from(SAMPLE),
  });
  await expect(page.getByRole("heading", { name: "Review artifact" })).toBeVisible();
}

test("empty library invites a first artifact", async ({ page }) => {
  await signedIn(page, "a-empty");
  await page.getByRole("link", { name: "Library", exact: true }).first().click();
  await expect(page).toHaveURL(/\/construct\/library$/);
  await expect(page.getByText("Nothing captured yet.")).toBeVisible();
  await expect(page.getByRole("link", { name: /add your first artifact/i })).toBeVisible();
});

test("upload inspects the file and drafts metadata without AI", async ({ page }) => {
  await signedIn(page, "a-upload");
  await upload(page);

  await expect(page.getByText("benchmark_001.txt").first()).toBeVisible();
  await expect(page.getByText("Awaiting review")).toBeVisible();
  await expect(page.getByText("no AI has read this artifact")).toBeVisible();
  // Title is drafted from the filename and says so.
  await expect(page.getByLabel("Title")).toHaveValue("benchmark_001");
  await expect(page.getByText(/Drafted from the filename/)).toBeVisible();
  // The deterministic preview is the real file content.
  await expect(page.getByText(/Digital Knowledge Twin/).first()).toBeVisible();
});

test("binary files are refused in this phase", async ({ page }) => {
  await signedIn(page, "a-binary");
  await page.goto("/construct/ingest");
  await page.locator('input[type="file"]').setInputFiles({
    name: "image.png", mimeType: "image/png",
    buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]),
  });
  await expect(page.getByTestId("form-error")).toContainText(/text artifacts/i);
});

test("review, register, and the artifact becomes trusted", async ({ page }) => {
  await signedIn(page, "a-register");
  await upload(page);

  await page.getByLabel("Title").fill("CEREBRO Digital Knowledge Twin");
  const topics = page.getByLabel("Topics");
  await topics.fill("Provenance");
  await topics.press("Enter");

  await page.getByRole("button", { name: /confirm and register/i }).click();

  await expect(page.getByText("Registered").first()).toBeVisible();
  await expect(page.getByText(/checksum-verified/i)).toBeVisible();
  // Fields lock once registered.
  await expect(page.getByLabel("Title")).toBeDisabled();

  await page.goto("/construct/library");
  await expect(page.getByText("CEREBRO Digital Knowledge Twin")).toBeVisible();
  await expect(page.getByText(/1 artifact · 1 registered/)).toBeVisible();
});

test("saving a draft does not register", async ({ page }) => {
  await signedIn(page, "a-draft");
  await upload(page);
  await page.getByLabel("Title").fill("Still a draft");
  await page.getByRole("button", { name: /save draft/i }).click();

  await expect(page.getByText("Saved")).toBeVisible();
  await expect(page.getByText("Awaiting review")).toBeVisible();

  await page.goto("/construct/library");
  await expect(page.getByText(/1 artifact · 0 registered/)).toBeVisible();
});

test("the same file cannot be added twice", async ({ page }) => {
  await signedIn(page, "a-dupe");
  await upload(page);
  await page.goto("/construct/ingest");
  await page.locator('input[type="file"]').setInputFiles({
    name: "copy.txt", mimeType: "text/plain", buffer: Buffer.from(SAMPLE),
  });
  await expect(page.getByTestId("form-error")).toContainText(/already in your library/i);
});

test("library and ingest are protected routes", async ({ page }) => {
  await page.context().clearCookies();
  for (const path of ["/construct/library", "/construct/ingest"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login/);
  }
});

test("one user never sees another user's artifacts", async ({ browser }) => {
  const a = await browser.newContext();
  const pageA = await a.newPage();
  await signUp(pageA, makeAccount("a-iso-a"));
  await pageA.waitForURL(/\/construct$/);
  await upload(pageA, "private-notes.txt");

  const b = await browser.newContext();
  const pageB = await b.newPage();
  await signUp(pageB, makeAccount("a-iso-b"));
  await pageB.waitForURL(/\/construct$/);
  await pageB.goto("/construct/library");

  await expect(pageB.getByText("Nothing captured yet.")).toBeVisible();
  expect((await pageB.textContent("body")) ?? "").not.toContain("private-notes");

  await a.close();
  await b.close();
});
