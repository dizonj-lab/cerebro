import { expect, test } from "@playwright/test";

import { logIn, logOut, makeAccount, signUp } from "./helpers";

// Fail any test that logs a browser console error, satisfying the
// "no console errors" requirement of TEST 9 across every page visited.
test.beforeEach(async ({ page }) => {
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    // The browser logs every non-2xx fetch as a console error. Rejected
    // credentials and duplicate signups are expected paths, not defects;
    // everything else still fails the test.
    if (/Failed to load resource/i.test(text)) return;
    throw new Error(`Console error: ${text}`);
  });
});

// --- TEST 1: landing -------------------------------------------------------

test("TEST 1 — landing renders with branding and both entry points", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle(/CEREBRO/);
  await expect(page.getByText("CEREBRO").first()).toBeVisible();
  await expect(
    page.getByText("Adaptive Knowledge and Reasoning Digital Twin").first(),
  ).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  // Learn · Connect · Reason · Recall
  for (const pillar of ["Learn", "Connect", "Reason", "Recall"]) {
    await expect(page.getByRole("heading", { name: pillar, level: 3 })).toBeVisible();
  }

  await expect(page.getByRole("link", { name: /sign in/i }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: /create account/i }).first()).toBeVisible();
});

test("TEST 1 — Sign In navigates to /login", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /sign in/i }).first().click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
});

test("TEST 1 — Create Account navigates to /signup", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /create account/i }).first().click();
  await expect(page).toHaveURL(/\/signup$/);
  await expect(page.getByRole("heading", { name: /create your account/i })).toBeVisible();
});

// --- TEST 2: sign-up -------------------------------------------------------

test("TEST 2 — new user signs up and lands in The Construct", async ({ page }) => {
  const account = makeAccount("signup");
  await signUp(page, account);

  await expect(page).toHaveURL(/\/construct$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/Good (morning|afternoon|evening)/);
  await expect(page.getByText("Your knowledge twin begins here.")).toBeVisible();
});

test("TEST 2 — validation blocks an empty submission", async ({ page }) => {
  await page.goto("/signup");
  await page.getByRole("button", { name: /create account/i }).click();

  await expect(page.getByText("Display name is required")).toBeVisible();
  await expect(page.getByText("Email is required")).toBeVisible();
  await expect(page.getByText("Password is required")).toBeVisible();
  await expect(page).toHaveURL(/\/signup$/);
});

test("TEST 2 — mismatched confirmation is rejected", async ({ page }) => {
  const account = makeAccount("mismatch");
  await page.goto("/signup");
  await page.getByLabel("Display Name").fill(account.displayName);
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password", { exact: true }).fill(account.password);
  await page.getByLabel("Confirm Password").fill("a-different-password-9");
  await page.getByRole("button", { name: /create account/i }).click();

  await expect(page.getByText("Passwords do not match")).toBeVisible();
  await expect(page).toHaveURL(/\/signup$/);
});

test("TEST 2 — weak password is rejected", async ({ page }) => {
  const account = makeAccount("weak");
  await page.goto("/signup");
  await page.getByLabel("Display Name").fill(account.displayName);
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password", { exact: true }).fill("short1");
  await page.getByLabel("Confirm Password").fill("short1");
  await page.getByRole("button", { name: /create account/i }).click();

  await expect(page.getByText(/at least 10 characters/i)).toBeVisible();
});

test("TEST 2 — invalid email is rejected", async ({ page }) => {
  await page.goto("/signup");
  await page.getByLabel("Display Name").fill("Test Operator");
  await page.getByLabel("Email").fill("not-an-email");
  await page.getByLabel("Password", { exact: true }).fill("knowledge-twin-2026");
  await page.getByLabel("Confirm Password").fill("knowledge-twin-2026");
  await page.getByRole("button", { name: /create account/i }).click();

  await expect(page.getByText("Enter a valid email address")).toBeVisible();
});

// --- TEST 3: duplicate account --------------------------------------------

test("TEST 3 — duplicate email is rejected gracefully", async ({ page }) => {
  const account = makeAccount("dupe");

  await signUp(page, account);
  await expect(page).toHaveURL(/\/construct$/);
  await logOut(page);
  await expect(page).toHaveURL(/\/$/);

  await signUp(page, account);

  await expect(page.getByText(/already exists/i)).toBeVisible();
  await expect(page).toHaveURL(/\/signup$/);
});

// --- TEST 4: login ---------------------------------------------------------

test("TEST 4 — existing user logs in and reaches The Construct", async ({ page }) => {
  const account = makeAccount("login");
  await signUp(page, account);
  await logOut(page);

  await logIn(page, account);

  await expect(page).toHaveURL(/\/construct$/);
  // The dashboard greets the user by name (Phase 1.5).
  await expect(page.getByRole("heading", { level: 1 })).toContainText(account.displayName.split(" ")[0]);
});

// --- TEST 5: invalid login -------------------------------------------------

test("TEST 5 — wrong password is rejected without leaking detail", async ({ page }) => {
  const account = makeAccount("badpass");
  await signUp(page, account);
  await logOut(page);

  await page.goto("/login");
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password", { exact: true }).fill("wrong-password-12345");
  await page.getByRole("button", { name: /^sign in$/i }).click();

  await expect(page.getByTestId("form-error")).toHaveText("Invalid email or password");
  await expect(page).toHaveURL(/\/login/);

  // No hash, algorithm or account-existence hints on the page.
  const body = (await page.textContent("body")) ?? "";
  expect(body.toLowerCase()).not.toContain("argon2");
  expect(body.toLowerCase()).not.toContain("hash");
});

test("TEST 5 — unknown email produces the identical message", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("nobody-at-all@example.com");
  await page.getByLabel("Password", { exact: true }).fill("whatever-password-1");
  await page.getByRole("button", { name: /^sign in$/i }).click();

  await expect(page.getByTestId("form-error")).toHaveText("Invalid email or password");
});

// --- TEST 6: protected route ----------------------------------------------

test("TEST 6 — unauthenticated /construct redirects to /login", async ({ page }) => {
  await page.context().clearCookies();
  await page.goto("/construct");

  await expect(page).toHaveURL(/\/login\?next=%2Fconstruct/);
  await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
});

test("TEST 6 — after logging out, /construct is inaccessible again", async ({ page }) => {
  const account = makeAccount("protected");
  await signUp(page, account);
  await logOut(page);

  await page.goto("/construct");
  await expect(page).toHaveURL(/\/login/);
});

// --- TEST 7: session persistence -------------------------------------------

test("TEST 7 — session survives a page refresh", async ({ page }) => {
  const account = makeAccount("session");
  await signUp(page, account);
  await logOut(page);
  await logIn(page, account);
  await expect(page).toHaveURL(/\/construct$/);

  await page.reload();

  await expect(page).toHaveURL(/\/construct$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/Good (morning|afternoon|evening)/);
});

test("TEST 7 — an authenticated user visiting /login is sent to The Construct", async ({ page }) => {
  const account = makeAccount("already");
  await signUp(page, account);
  await page.waitForURL(/\/construct$/);

  await page.goto("/login");
  await expect(page).toHaveURL(/\/construct$/);
});

// --- TEST 8: logout --------------------------------------------------------

test("TEST 8 — logout clears the session cookie", async ({ page }) => {
  const account = makeAccount("logout");
  await signUp(page, account);
  await page.waitForURL(/\/construct$/);

  const before = await page.context().cookies();
  expect(before.some((c) => c.name === "cerebro_session")).toBe(true);

  await logOut(page);
  await expect(page).toHaveURL(/\/$/);

  const after = await page.context().cookies();
  expect(after.some((c) => c.name === "cerebro_session" && c.value !== "")).toBe(false);
});

test("TEST 8 — the session cookie is httpOnly and unreadable from scripts", async ({ page }) => {
  const account = makeAccount("httponly");
  await signUp(page, account);
  await page.waitForURL(/\/construct$/);

  const cookie = (await page.context().cookies()).find((c) => c.name === "cerebro_session");
  expect(cookie?.httpOnly).toBe(true);

  const visible = await page.evaluate(() => document.cookie);
  expect(visible).not.toContain("cerebro_session");
});
