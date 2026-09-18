import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";

const PUBLIC_PAGES = ["/", "/login", "/signup"];

// --- TEST 9: accessibility -------------------------------------------------

for (const path of PUBLIC_PAGES) {
  test(`TEST 9 — ${path} has no WCAG A/AA violations`, async ({ page }) => {
    await page.goto(path);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    expect(
      results.violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`),
    ).toEqual([]);
  });
}

test("TEST 9 — The Construct has no WCAG A/AA violations", async ({ page }) => {
  await signUp(page, makeAccount("a11y"));
  await page.waitForURL(/\/construct$/);

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();

  expect(results.violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`)).toEqual([]);
});

test("TEST 9 — form controls are reachable and labelled", async ({ page }) => {
  await page.goto("/login");

  // Every input resolves to exactly one accessible label.
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toBeVisible();

  // Keyboard path: email -> password -> submit.
  await page.getByLabel("Email").focus();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Password", { exact: true })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: /^sign in$/i })).toBeFocused();
});

test("TEST 9 — focus is visibly indicated", async ({ page }) => {
  await page.goto("/login");
  const email = page.getByLabel("Email");
  await email.focus();

  const outline = await email.evaluate((el) => {
    const s = getComputedStyle(el);
    return { width: s.outlineWidth, style: s.outlineStyle };
  });
  expect(outline.style).not.toBe("none");
  expect(parseFloat(outline.width)).toBeGreaterThan(0);
});

// --- TEST 9: error and loading states --------------------------------------

test("TEST 9 — submit button shows a loading state", async ({ page }) => {
  const account = makeAccount("loading");

  // Hold the response open so the in-flight state is observable.
  await page.route("**/api/auth/signup", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 900));
    await route.continue();
  });

  await page.goto("/signup");
  await page.getByLabel("Display Name").fill(account.displayName);
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password", { exact: true }).fill(account.password);
  await page.getByLabel("Confirm Password").fill(account.password);

  const submit = page.getByRole("button", { name: /creating account|create account/i });
  await submit.click();

  await expect(submit).toHaveAttribute("aria-busy", "true");
  await expect(submit).toBeDisabled();
  await expect(page.getByText("Creating account")).toBeVisible();
});

test("TEST 9 — a network failure surfaces a readable message", async ({ page }) => {
  await page.route("**/api/auth/login", (route) => route.abort("failed"));

  await page.goto("/login");
  await page.getByLabel("Email").fill("someone@example.com");
  await page.getByLabel("Password", { exact: true }).fill("some-password-123");
  await page.getByRole("button", { name: /^sign in$/i }).click();

  await expect(page.getByTestId("form-error")).toContainText("Unable to reach CEREBRO");
});

// --- TEST 9: responsiveness ------------------------------------------------

const VIEWPORTS = [
  { name: "mobile", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 900 },
];

for (const viewport of VIEWPORTS) {
  test(`TEST 9 — public pages fit ${viewport.name} without horizontal scroll`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });

    for (const path of PUBLIC_PAGES) {
      await page.goto(path);
      const overflows = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      );
      expect(overflows, `${path} overflows at ${viewport.name}`).toBe(false);
    }
  });
}

test("TEST 9 — The Construct sidebar collapses on small screens", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signUp(page, makeAccount("responsive"));
  await page.waitForURL(/\/construct$/);

  const sidebar = page.locator("nav[aria-label='Workspace']");
  // Addressed by test id: the accessible name flips between open and closed.
  const toggle = page.getByTestId("sidebar-toggle");

  // Off-canvas by default. Polled, because the panel slides on a transition.
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveAccessibleName(/open navigation/i);
  await expect
    .poll(() => sidebar.evaluate((el) => el.getBoundingClientRect().right))
    .toBeLessThanOrEqual(1);

  await toggle.click();
  await expect(toggle).toHaveAccessibleName(/close navigation/i);
  await expect
    .poll(() => sidebar.evaluate((el) => el.getBoundingClientRect().left))
    .toBeGreaterThanOrEqual(0);

  const overflows = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  expect(overflows).toBe(false);
});

test("TEST 9 — The Construct is usable at desktop width", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await signUp(page, makeAccount("desktop"));
  await page.waitForURL(/\/construct$/);

  await expect(page.locator("nav[aria-label='Workspace']")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/Good (morning|afternoon|evening)/);

  for (const item of ["Library", "Ingest", "Search", "Recall", "Timeline", "Galaxy", "What-If"]) {
    await expect(
      page.locator("nav[aria-label='Workspace']").getByRole("button", { name: item, exact: true }),
    ).toBeVisible();
  }
});
