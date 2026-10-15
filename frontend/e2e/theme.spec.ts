import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

async function chooseTheme(page: import("@playwright/test").Page, label: string) {
  await page.goto("/construct/settings");
  await page.getByLabel("Appearance").selectOption({ label });
}

test("appearance can be set to dark, and survives a reload", async ({ page }) => {
  await signUp(page, makeAccount("theme-dark"));
  await page.waitForURL(/\/construct$/);

  await chooseTheme(page, "Dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  // Applied before paint on the next load, from the browser's copy.
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  // And it is the account that holds the choice, not just the browser.
  const prefs = await page.request.get("/api/preferences");
  expect((await prefs.json()).theme).toBe("dark");
});

test("a dark surface really is dark, not a light page with a flag set", async ({ page }) => {
  await signUp(page, makeAccount("theme-paint"));
  await page.waitForURL(/\/construct$/);
  await chooseTheme(page, "Dark");

  // The token actually re-points, so the painted background changes.
  const background = await page.evaluate(
    () => getComputedStyle(document.body).backgroundColor,
  );
  const [r, g, b] = background.match(/\d+/g)!.map(Number);
  expect(r + g + b).toBeLessThan(150); // near-black, not near-white
});

test("the dark theme has no WCAG A/AA violations", async ({ page }) => {
  await signUp(page, makeAccount("theme-a11y"));
  await page.waitForURL(/\/construct$/);
  await chooseTheme(page, "Dark");

  // A dark palette that fails contrast is worse than no dark palette: it
  // looks considered and is not.
  for (const path of ["/construct", "/construct/settings", "/construct/library"]) {
    await page.goto(path);
    const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    expect(
      results.violations.map((v) => `${path} ${v.id}: ${v.nodes.length} node(s)`),
    ).toEqual([]);
  }
});

test("choosing light pins light even when the system prefers dark", async ({ browser }) => {
  const context = await browser.newContext({ colorScheme: "dark" });
  const page = await context.newPage();
  await signUp(page, makeAccount("theme-light"));
  await page.waitForURL(/\/construct$/);

  await chooseTheme(page, "Light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  const background = await page.evaluate(
    () => getComputedStyle(document.body).backgroundColor,
  );
  const [r, g, b] = background.match(/\d+/g)!.map(Number);
  expect(r + g + b).toBeGreaterThan(700); // near-white despite the OS asking for dark
  await context.close();
});

test("matching the system follows the operating system", async ({ browser }) => {
  const context = await browser.newContext({ colorScheme: "dark" });
  const page = await context.newPage();
  await signUp(page, makeAccount("theme-system"));
  await page.waitForURL(/\/construct$/);

  // "system" is the default, and leaves the attribute off so the media query
  // stays in charge — including when the OS changes while the page is open.
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", /.*/);
  const background = await page.evaluate(
    () => getComputedStyle(document.body).backgroundColor,
  );
  const [r, g, b] = background.match(/\d+/g)!.map(Number);
  expect(r + g + b).toBeLessThan(150);
  await context.close();
});
