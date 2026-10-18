import { expect, test } from "@playwright/test";

import { makeAccount, signUp } from "./helpers";

/**
 * The embedding budget as a setting.
 *
 * The five numbers here decide whether a document can be embedded at all;
 * they were compiled-in constants until one of them silently failed a whole
 * registration. These tests hold the parts a user can see: the defaults are
 * visible without being stored, a combination that cannot work is refused
 * with the reason, and the change that orphans vectors says so before it is
 * saved.
 */

test.beforeEach(async ({ page }) => {
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    if (/Failed to load resource/i.test(msg.text())) return;
    throw new Error(`Console error: ${msg.text()}`);
  });
});

async function openEmbeddingSettings(page: import("@playwright/test").Page, prefix: string) {
  const account = makeAccount(prefix);
  await signUp(page, account);
  await page.waitForURL(/\/construct$/);
  await page.goto("/construct/settings");
  await page.getByRole("tab", { name: "Embedding" }).click();
  await expect(page.getByTestId("embedding-settings")).toBeVisible();
  return account;
}

test("the defaults in force are shown without being stored as choices", async ({ page }) => {
  await openEmbeddingSettings(page, "emb-default");

  // Blank fields, because nothing is overridden — but the budget actually in
  // use is visible as the placeholder, so the screen can answer "what size
  // will my document be cut at" before anything is typed.
  const target = page.getByLabel("Chunk size (tokens)");
  await expect(target).toHaveValue("");
  await expect(target).toHaveAttribute("placeholder", "350");
  await expect(page.getByLabel("Overlap (tokens)")).toHaveAttribute("placeholder", "50");
  await expect(page.getByLabel("Context limit (tokens)")).not.toHaveAttribute(
    "placeholder",
    "",
  );

  // Nothing to save until something changes.
  await expect(page.getByRole("button", { name: /save embedding settings/i })).toBeDisabled();
});

test("the five settings save and survive a reload", async ({ page }) => {
  await openEmbeddingSettings(page, "emb-save");

  await page.getByLabel("Model").fill("mxbai-embed-large:latest");
  await page.getByLabel("Dimensions").fill("1024");
  await page.getByLabel("Context limit (tokens)").fill("512");
  await page.getByLabel("Chunk size (tokens)").fill("350");
  await page.getByLabel("Overlap (tokens)").fill("50");
  await page.getByRole("button", { name: /save embedding settings/i }).click();

  await expect(page.getByTestId("form-error")).toBeHidden();
  // Saved values are now the user's own choice, and marked as such rather
  // than being indistinguishable from an inherited default.
  await expect(page.getByTestId("origin-embedding_model")).toContainText("Chosen by you");

  await page.reload();
  await page.getByRole("tab", { name: "Embedding" }).click();
  await expect(page.getByLabel("Model")).toHaveValue("mxbai-embed-large:latest");
  await expect(page.getByLabel("Chunk size (tokens)")).toHaveValue("350");
  await expect(page.getByLabel("Overlap (tokens)")).toHaveValue("50");
});

test("changing the model warns that existing vectors are left behind", async ({ page }) => {
  await openEmbeddingSettings(page, "emb-warn");

  // Nothing touched yet, so no warning.
  await expect(page.getByTestId("orphan-warning")).toBeHidden();

  await page.getByLabel("Model").fill("nomic-embed-text");
  await expect(page.getByTestId("orphan-warning")).toContainText(
    /drop out of semantic search/i,
  );

  // A chunking change is not a vector-space change, so it carries no warning.
  await page.getByLabel("Model").fill("");
  await page.getByLabel("Chunk size (tokens)").fill("300");
  await expect(page.getByTestId("orphan-warning")).toBeHidden();
});

test("a chunk larger than the context limit is refused with the reason", async ({ page }) => {
  await openEmbeddingSettings(page, "emb-refuse");

  await page.getByLabel("Context limit (tokens)").fill("512");
  await page.getByLabel("Chunk size (tokens)").fill("900");
  await page.getByRole("button", { name: /save embedding settings/i }).click();

  // The server checks the pair, so the message names the limit it clashed
  // with rather than saying the field is invalid.
  await expect(page.getByTestId("form-error")).toContainText("512");

  // Nothing was stored, so a reload comes back to the defaults.
  await page.reload();
  await page.getByRole("tab", { name: "Embedding" }).click();
  await expect(page.getByLabel("Chunk size (tokens)")).toHaveValue("");
});

test("a width the model does not produce is refused with the right one", async ({ page }) => {
  await openEmbeddingSettings(page, "emb-width");

  await page.getByLabel("Model").fill("mxbai-embed-large:latest");
  await page.getByLabel("Dimensions").fill("384");
  await page.getByRole("button", { name: /save embedding settings/i }).click();

  await expect(page.getByTestId("form-error")).toContainText("1024");
});

test("clearing a field returns it to the deployment default", async ({ page }) => {
  await openEmbeddingSettings(page, "emb-clear");

  await page.getByLabel("Chunk size (tokens)").fill("200");
  await page.getByRole("button", { name: /save embedding settings/i }).click();
  await expect(page.getByTestId("origin-chunk_target_tokens")).toContainText("Chosen by you");

  await page.getByLabel("Chunk size (tokens)").fill("");
  await page.getByRole("button", { name: /save embedding settings/i }).click();

  // Back to inherited: no badge, and the default visible as the placeholder.
  await expect(page.getByTestId("origin-chunk_target_tokens")).toBeHidden();
  await expect(page.getByLabel("Chunk size (tokens)")).toHaveAttribute("placeholder", "350");
});

test("discarding a change restores the saved values", async ({ page }) => {
  await openEmbeddingSettings(page, "emb-discard");

  await page.getByLabel("Chunk size (tokens)").fill("123");
  await page.getByRole("button", { name: /discard changes/i }).click();

  await expect(page.getByLabel("Chunk size (tokens)")).toHaveValue("");
  await expect(page.getByRole("button", { name: /save embedding settings/i })).toBeDisabled();
});
