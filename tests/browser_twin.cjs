// Smoke test of the twin: every view loads without page errors, the story plays a replay,
// decisions open the explainer, and nothing overflows at phone width.
// Run with the server on 127.0.0.1:8000:  node tests/browser_twin.cjs
const { chromium } = require(process.env.RAKSHAK_PLAYWRIGHT_MODULE || 'playwright');
const BASE = process.env.RAKSHAK_URL || 'http://127.0.0.1:8000';
(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = []; page.on('pageerror', (e) => errors.push(e.message));
  await page.addInitScript(() => localStorage.setItem('rakshak.scene', 'model'));   // no 3D-tile access needed
  await page.goto(`${BASE}/?debug#story`);
  await page.waitForFunction(() => window.__rakshak?.world, null, { timeout: 60000 });
  for (let i = 0; i < 4; i++) { await page.click('#story-next'); await page.waitForTimeout(1500); }
  await page.waitForFunction(() => !document.getElementById('explainer').hidden, null, { timeout: 60000 });
  const explainer = await page.textContent('#ex-body');
  for (const view of ['compare', 'explore', 'results', 'methods']) {
    await page.goto(`${BASE}/?debug#${view}`); await page.waitForTimeout(2500);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${BASE}/#story`); await page.waitForTimeout(3000);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  console.log(JSON.stringify({ errors, explainer: explainer.slice(0, 80), overflow }));
  if (errors.length || !explainer.trim() || overflow > 0) throw Error('twin smoke test failed');
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
