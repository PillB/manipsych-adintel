const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 375, height: 700 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  const url = 'https://pillb.github.io/manipsych-adintel/reports/adintel/adintel_dashboard.html';
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(2500);

  // Find elements wider than 375px (overflow)
  const overflowInfo = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const offenders = [];
    document.querySelectorAll('section, table, div, pre, code').forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.width > vw + 2 && r.right > vw + 2) {
        offenders.push({ tag: el.tagName, id: el.id, cls: el.className?.toString?.().slice(0,40), width: Math.round(r.width), right: Math.round(r.right) });
      }
    });
    return { viewportWidth: vw, overflowCount: offenders.length, top: offenders.slice(0, 10) };
  });
  console.log('overflow:', JSON.stringify(overflowInfo, null, 2));

  // Find truncated text via scrollWidth > clientWidth
  const truncation = await page.evaluate(() => {
    const trunc = [];
    document.querySelectorAll('h2, h3, h4, p, span, td, th, button, a').forEach(el => {
      if (el.scrollWidth > el.clientWidth + 4) {
        trunc.push({ tag: el.tagName, txt: el.textContent.trim().slice(0,60), scrollW: el.scrollWidth, clientW: el.clientWidth });
      }
    });
    return { count: trunc.length, top: trunc.slice(0, 10) };
  });
  console.log('truncation:', JSON.stringify(truncation, null, 2));

  // term-comparison table at 375px
  const tableInfo = await page.evaluate(() => {
    const tbls = document.querySelectorAll('.term-comparison-table, table');
    const out = [];
    tbls.forEach((t,i) => {
      if (i < 6) {
        const r = t.getBoundingClientRect();
        out.push({ i, cls: t.className?.slice(0,40), width: Math.round(r.width), scrollW: t.scrollWidth, hasHorizontalScroll: t.scrollWidth > t.clientWidth });
      }
    });
    return out;
  });
  console.log('tables:', JSON.stringify(tableInfo, null, 2));

  // Verdict banner contrast (sample one)
  const banner = await page.evaluate(() => {
    const b = document.querySelector('.verdict-banner');
    if (!b) return null;
    const cs = getComputedStyle(b);
    const txt = b.textContent.trim().slice(0,80);
    return { borderLeft: cs.borderLeftColor, bg: cs.backgroundColor, text: txt };
  });
  console.log('verdict banner sample:', JSON.stringify(banner));

  await browser.close();
})();
