// gfx_web_test.mjs -- draw a built Stride2D page in headless Chromium and write the exact picture as a PPM.
//
//   node tools/gfx_web_test.mjs --dir PAGE_DIR --gfx webgl2|webgpu --frames N --out FILE.ppm [--hardware] [--headed]
//
// PAGE_DIR holds index.html, stride2d_web.js and stride2d-player.wasm (what `python3 build.py gfx-web` or `player --web` writes). The page is served from
// http://localhost (WebGPU exists only in a secure context), run with the clock stopped (?manual=1), stepped N frames, and the canvas read back
// (state.readPixels, exact even on WebGPU) and written top row first. It prints one JSON line: the API that actually drew, and what the page logged.
//
// By default Chromium is given software rendering (SwiftShader, which has WebGL2 and a Vulkan device for WebGPU) so it runs where there is no GPU, such as CI;
// --hardware leaves that to the browser. Needs playwright-core (found in PLAYWRIGHT_CORE_DIR, `npm root -g`, or /opt/*/node_modules) and a Chromium
// (PLAYWRIGHT_BROWSERS_PATH, or CHROMIUM_PATH).
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { createRequire } from "node:module";
import { execSync } from "node:child_process";

function arg(name, dflt) {
  const i = process.argv.indexOf("--" + name);
  if (i < 0) return dflt;
  const v = process.argv[i + 1];
  return v === undefined || v.startsWith("--") ? true : v;
}
const dir = arg("dir"), gfx = arg("gfx", "webgl2"), frames = parseInt(arg("frames", "1"), 10), out = arg("out");
const hardware = arg("hardware", false);
const input = arg("input", false);       // instead of a picture: send the page mouse and keyboard input, and print what the module read back (the "ev" lines it logs)
let headed = arg("headed", false);
if (!dir || (!out && !input)) { console.error("usage: node gfx_web_test.mjs --dir PAGE_DIR --gfx webgl2|webgpu --frames N --out FILE.ppm [--hardware] [--headed]"); process.exit(2); }

function loadPlaywright() {
  const roots = [process.env.PLAYWRIGHT_CORE_DIR];
  try { roots.push(execSync("npm root -g", { encoding: "utf8" }).trim()); } catch {}
  roots.push("/opt/npm-tools/node_modules", "/opt/node-tools/node_modules");
  for (const r of roots.filter(Boolean)) {
    for (const pkg of ["playwright-core", "playwright"]) {
      try { return createRequire(path.join(r, "x.js"))(pkg); } catch {}
    }
  }
  console.error("gfx_web_test: playwright-core not found (npm i -g playwright-core, or set PLAYWRIGHT_CORE_DIR)");
  process.exit(3);
}
const { chromium } = loadPlaywright();

const MIME = { ".html": "text/html", ".js": "text/javascript", ".wasm": "application/wasm", ".json": "application/json" };
const server = http.createServer((req, res) => {
  const file = path.join(dir, decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (!file.startsWith(path.resolve(dir)) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.statusCode = 404; res.end("not found"); return; }
  res.setHeader("content-type", MIME[path.extname(file)] || "application/octet-stream");
  res.end(fs.readFileSync(file));
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));

// Software rendering, for a machine with no GPU. WebGL2 uses Chromium's own SwiftShader. WebGPU does NOT: SwiftShader's Vulkan cannot present to a canvas
// (configuring one loses the device: "A valid external Instance reference no longer exists"), so WebGPU uses the system's software Vulkan, Mesa's lavapipe
// (apt install mesa-vulkan-drivers), and needs a headed browser, which on a machine with no screen means running this under `xvfb-run -a`.
const args = [];
let needsDisplay = false;
if (!hardware) args.push("--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist");
if (gfx === "webgpu") {
  args.push("--enable-unsafe-webgpu", "--enable-features=Vulkan,WebGPU");
  if (!hardware) {
    needsDisplay = true;
    if (!process.env.VK_ICD_FILENAMES) {
      const icd = ["lvp_icd.json", "lvp_icd.x86_64.json"].map((f) => "/usr/share/vulkan/icd.d/" + f).find((f) => fs.existsSync(f));
      if (icd) process.env.VK_ICD_FILENAMES = icd;
    }
  }
}
if (needsDisplay && !headed) {
  if (!process.env.DISPLAY) {
    console.log(JSON.stringify({ ok: false, error: "software WebGPU needs a display: run under `xvfb-run -a node tools/gfx_web_test.mjs ...` (and apt install mesa-vulkan-drivers)" }));
    process.exit(4);
  }
  headed = true;
}
const launch = { headless: !headed, args };
if (process.env.CHROMIUM_PATH) launch.executablePath = process.env.CHROMIUM_PATH;
const browser = await chromium.launch(launch);
let result = { ok: false };
const logs = [];
try {
  const page = await browser.newPage();
  page.on("console", (m) => logs.push(m.text()));
  page.on("pageerror", (e) => logs.push("pageerror: " + e.message));
  await page.goto(`http://localhost:${server.address().port}/index.html?gfx=${gfx}&manual=1`);
  await page.waitForFunction(() => window.stride2dReady === true || (window.stride2d && window.stride2d.error), null, { timeout: 60000 });
  if (input) {
    const box = await page.locator("canvas").boundingBox();
    const at = (x, y) => [box.x + x, box.y + y];
    await page.mouse.move(...at(40, 30));
    await page.mouse.down();
    await page.mouse.up();
    await page.mouse.wheel(0, -100);                     // a notch up: dy +120
    await page.keyboard.press("a");
    await page.keyboard.press("Shift+A");
    await page.keyboard.press("Enter");
    await page.keyboard.press("ArrowLeft");
    await page.keyboard.press("Escape");
    await page.evaluate(() => window.stride2d.step(2));
    const shown = (await page.evaluate(() => document.getElementById("log").textContent)).split("\n");   // the page prints the module's stdout there
    const events = shown.filter((l) => l.startsWith("ev ")).map((l) => l.split(" ").slice(1).map(Number));
    console.log(JSON.stringify({ ok: true, backend: await page.evaluate(() => window.stride2d.backend), events, logs: logs.filter((l) => !l.startsWith("ev ")) }));
    await browser.close(); server.close();
    process.exit(0);
  }
  const info = await page.evaluate(async (n) => {
    const s = window.stride2d;
    if (s.error) return { error: s.error };
    s.step(n);
    const px = await s.readPixels();
    let bin = "";
    const chunk = 0x8000;
    for (let i = 0; i < px.rgba.length; i += chunk) bin += String.fromCharCode.apply(null, px.rgba.subarray(i, i + chunk));
    return { backend: s.backend, w: px.w, h: px.h, b64: btoa(bin) };
  }, frames);
  if (info.error) throw new Error(info.error);
  const rgba = Buffer.from(info.b64, "base64");           // rows bottom to top, RGBA
  const body = Buffer.alloc(info.w * info.h * 3);
  for (let y = 0; y < info.h; y++)
    for (let x = 0; x < info.w; x++) {
      const s = ((info.h - 1 - y) * info.w + x) * 4, d = (y * info.w + x) * 3;
      body[d] = rgba[s]; body[d + 1] = rgba[s + 1]; body[d + 2] = rgba[s + 2];
    }
  fs.writeFileSync(out, Buffer.concat([Buffer.from(`P6\n${info.w} ${info.h}\n255\n`), body]));
  result = { ok: true, backend: info.backend, requested: gfx, w: info.w, h: info.h, logs };
} catch (e) {
  result = { ok: false, error: String(e && e.message || e), logs };
} finally {
  await browser.close();
  server.close();
}
console.log(JSON.stringify(result));
process.exit(result.ok ? 0 : 1);
