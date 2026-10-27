// Record the CEREBRO demo tour as a 1080p video, scene by scene.
//
//   BASE=http://127.0.0.1:3300 OUT=out node demo/record.mjs
//
// Each scene in narration.json lasts at least its `seconds`, so its narration
// fits; if an action takes longer (a model thinking), the scene runs long and
// the real start time of every scene is written to scenes.json, which the
// voice script uses to place each line. Nothing here is faked: the documents
// are the seeded demo library and the answers come from the running models.
import { chromium } from "playwright";
import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE ?? "http://127.0.0.1:3300";
const OUT = resolve(process.env.OUT ?? join(here, "out"));
const THEME = process.env.THEME ?? "light";
const EMAIL = "demo@larkspur.example";
const PASSWORD = "larkspur-demo-2026";
const LIVE_FILE = join(here, "corpus/files/live/2026-04 Cold Storage Pilot Proposal.docx");
const narration = JSON.parse(readFileSync(join(here, "narration.json"), "utf8")).scenes;
const plan = Object.fromEntries(narration.map((s) => [s.id, s]));

mkdirSync(OUT, { recursive: true });
const W = 1920, H = 1080;

// A visible cursor, a chapter label and full-screen title cards, injected into
// every page. Video capture does not show the real pointer.
const overlay = () => {
  const style = document.createElement("style");
  style.textContent = `
    #demo-cursor { position: fixed; z-index: 2147483647; width: 22px; height: 22px; margin: -11px 0 0 -11px;
      border-radius: 50%; background: rgba(20,20,24,.28); border: 2px solid rgba(255,255,255,.95);
      box-shadow: 0 1px 6px rgba(0,0,0,.35); pointer-events: none; transition: transform .12s; left: -50px; top: -50px; }
    #demo-cursor.down { transform: scale(.7); background: rgba(15,118,110,.55); }
    #demo-chapter { position: fixed; z-index: 2147483646; left: 28px; bottom: 26px; padding: 9px 16px; border-radius: 999px;
      font: 600 17px system-ui, sans-serif; color: #fff; background: rgba(15,23,42,.78); backdrop-filter: blur(6px);
      opacity: 0; transition: opacity .5s; pointer-events: none; }
    #demo-card { position: fixed; inset: 0; z-index: 2147483645; display: flex; flex-direction: column; align-items: center;
      justify-content: center; gap: 18px; background: radial-gradient(ellipse at 50% 40%, #16233b 0%, #0a0f1a 70%);
      color: #f1f5f9; font-family: system-ui, sans-serif; opacity: 0; transition: opacity .8s; pointer-events: none; }
    #demo-card img { width: 128px; height: 128px; border-radius: 28px; background: #dbe5f3; padding: 10px; }
    #demo-card h1 { margin: 0; font-size: 64px; letter-spacing: .14em; font-weight: 700; }
    #demo-card p { margin: 0; font-size: 26px; color: #cbd5e1; }
    #demo-card small { margin-top: 26px; font-size: 17px; color: #94a3b8; }`;
  const mount = () => {
    if (document.getElementById("demo-cursor")) return;
    document.head.appendChild(style);
    const cursor = Object.assign(document.createElement("div"), { id: "demo-cursor" });
    const chapter = Object.assign(document.createElement("div"), { id: "demo-chapter" });
    const card = Object.assign(document.createElement("div"), { id: "demo-card" });
    document.body.append(cursor, chapter, card);
    addEventListener("mousemove", (e) => { cursor.style.left = e.clientX + "px"; cursor.style.top = e.clientY + "px"; }, true);
    addEventListener("mousedown", () => cursor.classList.add("down"), true);
    addEventListener("mouseup", () => cursor.classList.remove("down"), true);
    const saved = sessionStorage.getItem("demo-chapter");
    if (saved) { chapter.textContent = saved; chapter.style.opacity = "1"; }
  };
  window.__demo = {
    chapter(text) {
      sessionStorage.setItem("demo-chapter", text || "");
      const el = document.getElementById("demo-chapter");
      if (!el) return;
      el.style.opacity = "0";
      setTimeout(() => { el.textContent = text; el.style.opacity = text ? "1" : "0"; }, 250);
    },
    card(html) {
      const el = document.getElementById("demo-card");
      if (!el) return;
      if (html) el.innerHTML = html;
      el.style.opacity = html ? "1" : "0";
    },
  };
  if (document.body) mount(); else addEventListener("DOMContentLoaded", mount);
};

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: W, height: H },
  deviceScaleFactor: 1,
  colorScheme: THEME,
  recordVideo: { dir: OUT, size: { width: W, height: H } },
});
await context.addInitScript(overlay);
// Signed in before the camera rolls; the login screen is not the story.
const signIn = await context.request.post(`${BASE}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
if (!signIn.ok()) throw new Error(`Demo sign-in failed (${signIn.status()}); run demo/seed.py first.`);

const page = await context.newPage();
const t0 = Date.now();
const log = [];
const pause = (ms) => page.waitForTimeout(ms);

let pointer = { x: W / 2, y: H / 2 };
async function moveTo(x, y, steps = 28) {
  await page.mouse.move(x, y, { steps });
  pointer = { x, y };
}
async function point(locator, { click = true, dx = 0, dy = 0 } = {}) {
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  const box = await locator.boundingBox();
  if (!box) return false;
  await moveTo(box.x + box.width / 2 + dx, box.y + box.height / 2 + dy);
  await pause(250);
  if (click) await page.mouse.click(pointer.x, pointer.y);
  return true;
}
async function type(locator, text) {
  await point(locator);
  await locator.pressSequentially(text, { delay: 55 });
}
const chapter = (text) => page.evaluate((t) => window.__demo?.chapter(t), text);
const card = (html) => page.evaluate((h) => window.__demo?.card(h), html);
async function scroll(by, steps = 12) {
  for (let i = 0; i < steps; i++) { await page.mouse.wheel(0, by / steps); await pause(60); }
}

async function scene(id, run) {
  const s = plan[id];
  const start = Date.now();
  log.push({ id, start: (start - t0) / 1000, planned: s.seconds });
  console.log(`[${((start - t0) / 1000).toFixed(1)}s] ${id}`);
  try {
    await run();
  } catch (error) {
    console.warn(`   ${id}: ${error.message.split("\n")[0]}`);
  }
  const left = s.seconds * 1000 - (Date.now() - start);
  if (left > 0) await pause(left);
  log[log.length - 1].actual = (Date.now() - start) / 1000;
}

const brand = `<img src="/brand/cerebro-mark.png" alt=""><h1>CEREBRO</h1>`;

await page.goto(`${BASE}/construct`);
await page.waitForLoadState("networkidle");

await scene("intro", async () => {
  await card(`${brand}<p>Your private knowledge twin</p><small>Demo · Larkspur Logistics is a fictional company. All documents are invented.</small>`);
  await pause(plan.intro.seconds * 1000 - 1200);
  await card("");
});

await scene("dashboard", async () => {
  await chapter("Dashboard");
  await moveTo(700, 420);
  await pause(1500);
  await scroll(500);
  await pause(2500);
  await scroll(-500);
});

await scene("library", async () => {
  await point(page.getByRole("link", { name: "Library", exact: true }).first());
  await page.waitForURL(/library/);
  await chapter("Library");
  await pause(1500);
  const rows = page.getByTestId("row-registered");
  for (let i = 0; i < Math.min(4, await rows.count()); i++) {
    await point(rows.nth(i), { click: false });
    await pause(900);
  }
});

await scene("ingest", async () => {
  await point(page.getByRole("link", { name: "Ingest", exact: true }).first());
  await page.waitForURL(/ingest/);
  await chapter("Adding a document");
  await pause(1200);
  await page.locator('input[type="file"]').setInputFiles(LIVE_FILE);
  await page.getByRole("heading", { name: "Review artifact" }).waitFor({ timeout: 60000 });
  await pause(2500);
  await point(page.getByLabel("Title"), { click: false });
  await pause(2000);
  const suggest = page.getByRole("button", { name: /Suggest with local AI/ });
  if ((await suggest.count()) && (await suggest.isEnabled())) {
    await point(suggest);
    // The model's suggestions arrive in the form; give them time.
    await page.getByText(/Suggested by/).first().waitFor({ timeout: 40000 }).catch(() => {});
    await pause(2500);
  }
  const topics = page.getByLabel("Topics");
  await point(topics, { click: false });
  await pause(1500);
  await type(topics, "Operations");
  await page.keyboard.press("Enter");
  await pause(1500);
  await point(page.getByRole("button", { name: /confirm and register/i }));
  await page.getByText("Registered").first().waitFor({ timeout: 60000 });
  await pause(2000);
});

await scene("search", async () => {
  await chapter("Search");
  const box = page.getByRole("combobox", { name: "Search your knowledge" });
  await type(box, "robots that handle soft packaging");
  await page.keyboard.press("Enter");
  await page.waitForURL(/search/);
  await page.getByTestId("knowledge-result").first().waitFor({ timeout: 30000 });
  await pause(1500);
  const results = page.getByTestId("knowledge-result");
  for (let i = 0; i < Math.min(3, await results.count()); i++) {
    await point(results.nth(i), { click: false });
    await pause(1800);
  }
  // Leave the header search empty for the scenes that follow.
  await box.fill("");
});

await scene("galaxy", async () => {
  await point(page.getByRole("link", { name: /Galaxy/ }).first());
  await page.waitForURL(/galaxy/);
  await chapter("Knowledge Galaxy");
  await page.getByRole("application", { name: "Knowledge Galaxy" }).waitFor();
  await pause(3000);
  for (const name of ["Robotics", "Operations", "Finance"]) {
    await point(page.getByRole("button", { name: `${name}, cluster`, exact: true }), { click: false });
    await pause(2200);
  }
  await point(page.getByRole("button", { name: "Robotics, cluster", exact: true }));
  await pause(3500);
  const fragment = page.getByRole("button", { name: /, fragment$/ }).first();
  if (await fragment.count()) {
    await point(fragment, { click: false });
    await pause(3500);
  }
});

await scene("whatif", async () => {
  await chapter("What if");
  await type(page.getByLabel("Place an idea in your Galaxy"), "battery life in freezing warehouses");
  await point(page.getByRole("button", { name: "Place", exact: true }));
  await pause(2500);
  const lens = page.getByTestId("lens-node");
  if (await lens.count()) await point(lens, { click: false });
  await pause(2500);
});

await scene("timeline", async () => {
  await point(page.getByRole("link", { name: /Timeline/ }).first());
  await page.waitForURL(/timeline/);
  await chapter("Timeline");
  await page.getByTestId("timeline-event").first().waitFor({ timeout: 30000 });
  await pause(3000);
  const box = await page.getByTestId("navigator-window").boundingBox();
  if (box) {
    const y = box.y + box.height / 2;
    await moveTo(box.x + box.width / 2, y);
    await page.mouse.down();
    await moveTo(box.x + box.width / 2 - 520, y, 60);
    await pause(800);
    await moveTo(box.x + box.width / 2 + 260, y, 80);
    await page.mouse.up();
  }
  await pause(2000);
  const events = page.getByTestId("timeline-event");
  for (let i = 0; i < Math.min(3, await events.count()); i++) {
    await point(events.nth(i), { click: false });
    await pause(1200);
  }
});

await scene("ask", async () => {
  await chapter("Ask CEREBRO");
  await point(page.getByRole("button", { name: /Ask CEREBRO/ }).first());
  await type(page.getByLabel("Ask or describe what you're looking for"),
    "How did picks per labour hour change from the pilot to FreshCart?");
  await point(page.getByRole("button", { name: "Send" }));
  await page.getByTestId("chat-source").first().waitFor({ timeout: 90000 });
  await pause(6000);
  const source = page.getByTestId("chat-source").first();
  await point(source, { click: false });
  await pause(2500);
  await point(source.getByTestId("source-galaxy"));
  await pause(5000);
  await point(page.getByTestId("chat-source").first().getByTestId("source-timeline"));
  await pause(5000);
});

await scene("local", async () => {
  await point(page.getByRole("link", { name: "Settings", exact: true }).first());
  await page.waitForURL(/settings/).catch(() => {});
  await chapter("Runs locally");
  await pause(1500);
  const models = page.getByTestId("embedding-settings");
  if (await models.count()) await point(models, { click: false });
});

await scene("outro", async () => {
  await chapter("");
  await card(`${brand}<p>Learn · Connect · Reason · Recall</p><small>Larkspur Logistics is fictional. Built and evaluated on a self-hosted GPU.</small>`);
});

const video = page.video();
await context.close();
await browser.close();
const path = await video.path();
renameSync(path, join(OUT, "demo.webm"));
writeFileSync(join(OUT, "scenes.json"), JSON.stringify({ base: BASE, theme: THEME, scenes: log }, null, 1));
console.log(`video: ${join(OUT, "demo.webm")}`);
for (const s of log) if (s.actual > s.planned + 0.5) console.log(`   ${s.id} ran ${s.actual.toFixed(1)}s (planned ${s.planned}s)`);
