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
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/Welcome back/);

  const nav = page.locator("nav[aria-label='Workspace']");

  // Wired-up destinations are links.
  for (const item of [
    "Library",
    "Ingest",
    "Search",
    "Galaxy",
    "Timeline",
    "Profile",
    "Settings",
  ]) {
    await expect(nav.getByRole("link", { name: item, exact: true })).toBeVisible();
  }

  // Still inert placeholders for later work packages. The menu is the one in
  // the approved dashboard design; these have no routes yet.
  for (const item of [
    "Assisted Recollection",
    "Collections",
    "Tags",
    "Agents",
    "Help",
  ]) {
    await expect(nav.getByRole("button", { name: item, exact: true })).toBeVisible();
  }
});

test("the sidebar collapses to icons and stays that way", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await signUp(page, makeAccount("rail"));
  await page.waitForURL(/\/construct$/);

  const nav = page.locator("nav[aria-label='Workspace']");
  const label = nav.getByRole("link", { name: "Library", exact: true });
  await expect(label).toBeVisible();
  const wide = (await nav.boundingBox())!.width;

  await page.getByRole("button", { name: "Collapse navigation" }).click();
  expect((await nav.boundingBox())!.width).toBeLessThan(wide);
  // The link is still there and still named, just not shown as text.
  await expect(label).toBeVisible();

  // Remembered per browser, so it does not reopen on every navigation.
  await page.goto("/construct/library");
  await expect(page.getByRole("button", { name: "Expand navigation" })).toBeVisible();
  expect((await nav.boundingBox())!.width).toBeLessThan(wide);
});

test("the Galaxy opens with the navigation railed, and respects a manual width", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await signUp(page, makeAccount("rail-galaxy"));
  await page.waitForURL(/\/construct$/);

  const nav = page.locator("nav[aria-label='Workspace']");
  const wide = (await nav.boundingBox())!.width;

  // The visualisation wants the screen, so it defaults to the rail.
  await page.goto("/construct/galaxy");
  await expect(page.getByRole("button", { name: "Expand navigation" })).toBeVisible();
  const railed = (await nav.boundingBox())!.width;
  expect(railed).toBeLessThan(wide);
  // 64px, and the icons are still links.
  expect(railed).toBeLessThanOrEqual(64);
  await expect(nav.getByRole("link", { name: "Library", exact: true })).toBeVisible();

  // Having asked for labels here, the user keeps them: a stored choice wins
  // on every route, and the Galaxy's default never takes it back.
  await page.getByRole("button", { name: "Expand navigation" }).click();
  expect((await nav.boundingBox())!.width).toBe(wide);
  await page.goto("/construct/library");
  await page.goto("/construct/galaxy");
  expect((await nav.boundingBox())!.width).toBe(wide);
});

test("a railed icon is still named, by tooltip and to a screen reader", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await signUp(page, makeAccount("rail-names"));
  await page.waitForURL(/\/construct$/);

  await page.getByRole("button", { name: "Collapse navigation" }).click();
  const library = page
    .locator("nav[aria-label='Workspace']")
    .getByRole("link", { name: "Library", exact: true });
  await expect(library).toHaveAttribute("title", "Library");
  await expect(library).toBeVisible();

  // The active item is still marked as such with its label hidden.
  await library.click();
  await page.waitForURL(/\/construct\/library$/);
  await expect(library).toHaveAttribute("aria-current", "page");
});

test("a tablet gets the icon rail rather than a drawer over the workspace", async ({ page }) => {
  await page.setViewportSize({ width: 834, height: 1112 });
  await signUp(page, makeAccount("rail-tablet"));
  await page.waitForURL(/\/construct$/);

  const nav = page.locator("nav[aria-label='Workspace']");
  // Visible without a hamburger, and narrow enough to leave the workspace.
  await expect(nav).toBeVisible();
  expect((await nav.boundingBox())!.width).toBeLessThanOrEqual(64);
  await expect(nav.getByRole("link", { name: "Galaxy", exact: true })).toBeVisible();

  const overflows = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  expect(overflows).toBe(false);
});

test("the landing page offers the demo beside Create Account, in a dialog that closes", async ({ page }) => {
  // The video is served by the portfolio site; the test only needs the player, not the file.
  // The video request is left pending (as a slow network would); the subtitles are answered.
  await page.route("https://folio.xtangent.ai/**/*.mp4", () => {});
  await page.route("https://folio.xtangent.ai/**/*.vtt", (route) =>
    route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/vtt", "Access-Control-Allow-Origin": "*" },
      body: "WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.000\nHello\n",
    }),
  );
  await page.goto("/");
  const hero = page.locator("main section").first();
  const buttons = hero.getByRole("button", { name: "Watch demo" });
  await expect(buttons).toBeVisible();
  // Beside Create Account: the next control after it in the hero.
  const order = await hero.getByRole("button").allInnerTexts();
  expect(order.findIndex((t) => /Watch demo/.test(t))).toBe(order.findIndex((t) => /Create Account/.test(t)) + 1);

  await buttons.click();
  const dialog = page.getByRole("dialog", { name: "CEREBRO demo" });
  await expect(dialog).toBeVisible();
  const video = dialog.getByTestId("demo-video");
  await expect(video).toHaveAttribute("src", /cerebro-demo\.mp4$/);
  // Plain cross-origin media: playing must not depend on the CDN passing CORS headers through.
  await expect(video).not.toHaveAttribute("crossorigin", /.*/);
  // The subtitles arrive as a same-origin blob.
  await expect(video.locator("track")).toHaveAttribute("src", /^blob:/);
  await expect(page.getByRole("button", { name: "Close the demo" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});

test("when the demo video cannot load, the dialog offers folio's player instead", async ({ page }) => {
  await page.route("https://folio.xtangent.ai/**", (route) => route.fulfill({ status: 404 }));
  await page.goto("/");
  await page.locator("main section").first().getByRole("button", { name: "Watch demo" }).click();
  const dialog = page.getByRole("dialog", { name: "CEREBRO demo" });
  await expect(dialog.getByText("The video could not load here.")).toBeVisible();
  await expect(dialog.getByRole("link", { name: "Watch it on folio.xtangent.ai" })).toHaveAttribute(
    "href",
    "https://folio.xtangent.ai/demo/cerebro/",
  );
});
