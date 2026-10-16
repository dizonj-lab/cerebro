import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

async function chooseTheme(page: import("@playwright/test").Page, label: string) {
  await page.goto("/construct/settings");
  await page.getByLabel("Appearance", { exact: true }).selectOption({ label });
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

test("appearance toggles in the header without leaving the page", async ({ page }) => {
  await signUp(page, makeAccount("theme-header"));
  await page.waitForURL(/\/construct$/);

  // Somewhere the old control would have been especially costly to reach:
  // the Galaxy, whose view the user has arranged.
  await page.goto("/construct/galaxy");
  const toggle = page.getByTestId("theme-toggle");
  await expect(toggle).toHaveAccessibleName("Switch to dark appearance");

  // A marker that only survives if the document is never replaced.
  await page.evaluate(() => {
    (window as unknown as { __kept?: boolean }).__kept = true;
  });

  await toggle.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  // Still on the Galaxy: no navigation, nothing reloaded.
  expect(new URL(page.url()).pathname).toBe("/construct/galaxy");
  expect(
    await page.evaluate(() => (window as unknown as { __kept?: boolean }).__kept),
  ).toBe(true);

  // The button now offers the way back, and takes it.
  await expect(toggle).toHaveAccessibleName("Switch to light appearance");
  await toggle.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("a toggled appearance reaches the account and the Settings control", async ({ page }) => {
  await signUp(page, makeAccount("theme-sync"));
  await page.waitForURL(/\/construct$/);

  await page.getByTestId("theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await expect
    .poll(async () => (await (await page.request.get("/api/preferences")).json()).theme)
    .toBe("dark");

  // Settings agrees, rather than showing a stale "Match my system".
  await page.goto("/construct/settings");
  await expect(page.getByLabel("Appearance", { exact: true })).toHaveValue("dark");
});
