import type { Page } from "@playwright/test";

/** A fresh address per test run, so reruns never collide on the unique index. */
export function uniqueEmail(prefix = "user"): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 10_000)}@example.com`;
}

export interface TestAccount {
  displayName: string;
  email: string;
  password: string;
}

export function makeAccount(prefix = "user"): TestAccount {
  return {
    displayName: "Test Operator",
    email: uniqueEmail(prefix),
    password: "knowledge-twin-2026",
  };
}

export async function signUp(page: Page, account: TestAccount) {
  await page.goto("/signup");
  await page.getByLabel("Display Name").fill(account.displayName);
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password", { exact: true }).fill(account.password);
  await page.getByLabel("Confirm Password").fill(account.password);
  await page.getByRole("button", { name: /create account/i }).click();
}

export async function logIn(page: Page, account: TestAccount) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password", { exact: true }).fill(account.password);
  await page.getByRole("button", { name: /^sign in$/i }).click();
}

export async function logOut(page: Page) {
  // The sidebar Logout is always present on desktop widths.
  await page.locator("nav[aria-label='Workspace']").getByRole("button", { name: /logout/i }).click();
}
