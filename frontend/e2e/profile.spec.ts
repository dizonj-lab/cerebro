import { expect, test } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";

test.beforeEach(async ({ page }) => {
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    if (/Failed to load resource/i.test(msg.text())) return;
    throw new Error(`Console error: ${msg.text()}`);
  });
});

async function signedIn(page: import("@playwright/test").Page, prefix: string) {
  const account = makeAccount(prefix);
  await signUp(page, account);
  await page.waitForURL(/\/construct$/);
  return account;
}

// --- empty state -----------------------------------------------------------

test("new user sees a complete-your-profile prompt, not a broken widget", async ({ page }) => {
  await signedIn(page, "p-empty");
  await expect(
    page.getByText("Complete your profile to help CEREBRO understand your context."),
  ).toBeVisible();
  await expect(page.getByRole("progressbar", { name: /profile completion/i })).toHaveAttribute(
    "aria-valuenow",
    "0",
  );
});

// --- profile round trip ----------------------------------------------------

test("profile saves, persists across logout, and drives the dashboard", async ({ page }) => {
  const account = await signedIn(page, "p-save");

  await page.getByRole("link", { name: "Profile", exact: true }).first().click();
  await expect(page).toHaveURL(/\/construct\/profile$/);

  await page.getByLabel("Full name").fill("Joel Dizon");
  await page.getByLabel("Role or title").fill("Chief Architect");
  await page.getByLabel("Organization").fill("Dizon Lab");
  await page.getByLabel("Years of experience").fill("18");

  const expertise = page.getByLabel("Areas of expertise");
  await expertise.fill("AI Systems");
  await expertise.press("Enter");
  await expertise.fill("Enterprise Architecture");
  await expertise.press("Enter");
  // Case-insensitive duplicate must be dropped.
  await expertise.fill("ai systems");
  await expertise.press("Enter");

  await page.getByRole("button", { name: /save profile/i }).click();
  await expect(page.getByText("Profile saved")).toBeVisible();

  await expect(page.getByText("AI Systems")).toHaveCount(1);

  // Survives a full sign-out / sign-in cycle.
  await page.locator("nav[aria-label='Workspace']").getByRole("button", { name: /logout/i }).click();
  await page.waitForURL(/\/$/);
  await page.goto("/login");
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password", { exact: true }).fill(account.password);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await page.waitForURL(/\/construct$/);

  await expect(page.getByRole("heading", { level: 1 })).toContainText("Joel");
  await expect(page.getByText(/AI Systems/)).toBeVisible();

  const meter = page.getByRole("progressbar", { name: /profile completion/i }).first();
  const percent = Number(await meter.getAttribute("aria-valuenow"));
  expect(percent).toBeGreaterThan(0);
  expect(percent).toBeLessThan(100);
});

test("invalid profile input is rejected", async ({ page }) => {
  await signedIn(page, "p-invalid");
  await page.goto("/construct/profile");
  await page.getByLabel("Years of experience").fill("500");
  await page.getByRole("button", { name: /save profile/i }).click();
  await expect(page.getByTestId("form-error")).toBeVisible();
});

// --- preferences and AI privacy -------------------------------------------

test("preferences persist and default to private and local", async ({ page }) => {
  const account = await signedIn(page, "p-prefs");
  await page.goto("/construct/settings");

  await expect(page.getByLabel("Preferred response style")).toHaveValue("balanced");
  await expect(page.getByRole("switch", { name: "Keep knowledge private" })).toHaveAttribute(
    "aria-checked",
    "true",
  );

  await page.getByLabel("Preferred response style").selectOption("concise");
  await page.getByRole("switch", { name: "AI suggestions" }).click();

  await page.getByRole("tab", { name: "AI & Privacy" }).click();
  await expect(page.getByRole("radio", { name: /Local AI/ })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await expect(page.getByText("Processing stays within CEREBRO")).toBeVisible();

  // Persist across a sign-in cycle.
  await page.locator("nav[aria-label='Workspace']").getByRole("button", { name: /logout/i }).click();
  await page.waitForURL(/\/$/);
  await page.goto("/login");
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password", { exact: true }).fill(account.password);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await page.waitForURL(/\/construct$/);
  await page.goto("/construct/settings");

  await expect(page.getByLabel("Preferred response style")).toHaveValue("concise");
  await expect(page.getByRole("switch", { name: "AI suggestions" })).toHaveAttribute(
    "aria-checked",
    "false",
  );
});

test("cloud AI requires consent, and cancelling keeps local", async ({ page }) => {
  await signedIn(page, "p-consent");
  await page.goto("/construct/settings");
  await page.getByRole("tab", { name: "AI & Privacy" }).click();

  await page.getByRole("radio", { name: /Cloud AI/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("relevant portions of your content may be transmitted");

  await dialog.getByRole("button", { name: /^cancel$/i }).click();
  await expect(page.getByRole("radio", { name: /Local AI/ })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await expect(page.getByText("Processing stays within CEREBRO")).toBeVisible();

  // Now accept.
  await page.getByRole("radio", { name: /Cloud AI/ }).click();
  await page.getByRole("button", { name: /enable cloud ai/i }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByText("External processing enabled")).toBeVisible();

  // Switching back to local is always available.
  await page.getByRole("radio", { name: /Local AI/ }).click();
  await expect(page.getByText("Processing stays within CEREBRO")).toBeVisible();
});

// --- account ---------------------------------------------------------------

test("account shows safe fields and password can be changed", async ({ page }) => {
  const account = await signedIn(page, "p-account");
  await page.goto("/construct/settings");
  await page.getByRole("tab", { name: "Account" }).click();

  await expect(page.getByText(account.email)).toBeVisible();
  const body = (await page.textContent("body")) ?? "";
  expect(body.toLowerCase()).not.toContain("argon2");
  expect(body.toLowerCase()).not.toContain("password_hash");

  await page.getByLabel("Current password").fill(account.password);
  await page.getByLabel("New password", { exact: true }).fill("replacement-secret-2026");
  await page.getByLabel("Confirm new password").fill("replacement-secret-2026");
  await page.getByRole("button", { name: /update password/i }).click();
  await expect(page.getByText("Password updated")).toBeVisible();

  await page.locator("nav[aria-label='Workspace']").getByRole("button", { name: /logout/i }).click();
  await page.waitForURL(/\/$/);
  await page.goto("/login");
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password", { exact: true }).fill("replacement-secret-2026");
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await expect(page).toHaveURL(/\/construct$/);
});

// --- access control --------------------------------------------------------

test("profile and settings are protected routes", async ({ page }) => {
  await page.context().clearCookies();
  for (const path of ["/construct/profile", "/construct/settings"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login/);
  }
});

test("one user never sees another user's profile", async ({ browser }) => {
  const first = await browser.newContext();
  const firstPage = await first.newPage();
  await signUp(firstPage, makeAccount("p-iso-a"));
  await firstPage.waitForURL(/\/construct$/);
  await firstPage.goto("/construct/profile");
  await firstPage.getByLabel("Full name").fill("First Person");
  await firstPage.getByRole("button", { name: /save profile/i }).click();
  await expect(firstPage.getByText("Profile saved")).toBeVisible();

  const second = await browser.newContext();
  const secondPage = await second.newPage();
  await signUp(secondPage, makeAccount("p-iso-b"));
  await secondPage.waitForURL(/\/construct$/);
  await secondPage.goto("/construct/profile");

  await expect(secondPage.getByLabel("Full name")).toHaveValue("");
  expect((await secondPage.textContent("body")) ?? "").not.toContain("First Person");

  await first.close();
  await second.close();
});
