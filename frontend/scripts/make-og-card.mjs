// Regenerates public/og-card.png (1200x630), the image social networks show for a shared link.
//   node scripts/make-og-card.mjs
import { chromium } from "@playwright/test";

const html = `<!doctype html><meta charset="utf-8"><style>
  html,body{margin:0;width:1200px;height:630px;background:#fff;color:#1a1a1a;font-family:Geist,"Helvetica Neue",Arial,sans-serif}
  main{box-sizing:border-box;height:630px;padding:72px 84px;display:flex;flex-direction:column;justify-content:space-between;border-top:14px solid #2b66a8}
  .brand{font-size:34px;letter-spacing:-.01em}.brand b{font-weight:700}.brand span{color:#5c5c5c}
  h1{margin:0;font-size:84px;line-height:1.04;letter-spacing:-.03em;max-width:980px}
  p{margin:0;font-size:30px;line-height:1.35;color:#5c5c5c;max-width:900px}
  .src{font-size:24px;color:#5c5c5c;border-top:2px solid #1a1a1a;padding-top:18px}
</style><main>
  <div class="brand"><b>NZ Stats</b> <span>Intelligence</span></div>
  <div><h1>New Zealand's economy, explained.</h1><p style="margin-top:24px">Prices, card spending and migration, from official Stats NZ releases.</p></div>
  <div class="src">Source: Stats NZ, CC BY 4.0. Independent of, and not endorsed by, Stats NZ.</div>
</main>`;

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
  await page.setContent(html);
  await page.screenshot({ path: "public/og-card.png" });
} finally {
  await browser.close();
}
