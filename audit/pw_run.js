const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERR: ' + e.message));
  page.on('console', msg => { if (msg.type() === 'error') errors.push('CONSOLE.ERROR: ' + msg.text().slice(0,200)); });
  const url = 'https://pillb.github.io/manipsych-adintel/reports/adintel/adintel_dashboard.html';
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(3000);

  // 1) verify per_ad count in DOM
  const perAdCount = await page.evaluate(() => {
    const script = document.getElementById('solarize-summary');
    if (!script) return 'no #solarize-summary script tag';
    try {
      const data = JSON.parse(script.textContent);
      return { per_ad_selector: data.per_ad_selector?.length, n_outlier: data.outlier_term_comparison?.outlier_vs_all_non_outlier?.n_outlier, n_control: data.outlier_term_comparison?.outlier_vs_all_non_outlier?.n_control, cluster_count: data.clustering?.clusters?.length, build_fingerprint: data.build_fingerprint };
    } catch (e) { return 'parse error: ' + e.message; }
  });
  console.log('perAd data:', JSON.stringify(perAdCount));

  // 2) scroll into clustering section, count rendered cluster cards
  const clusterCardInfo = await page.evaluate(() => {
    const cards = document.querySelectorAll('.cluster-card');
    const results = [];
    cards.forEach(c => {
      const id = c.dataset.clusterId;
      const examples = c.querySelectorAll('.cluster-example');
      const termChips = c.querySelectorAll('.term-chip');
      const h4 = c.querySelector('h4');
      results.push({ id, examples_count: examples.length, term_count: termChips.length, heading: h4?.textContent?.trim()?.slice(0,80) });
    });
    return results;
  });
  console.log('cluster cards:', JSON.stringify(clusterCardInfo, null, 2));

  // 3) click on cluster card itself to see if it filters selector
  const clickResult = await page.evaluate(() => {
    const card = document.querySelector('.cluster-card');
    if (!card) return 'no card';
    const before = document.getElementById('adintel-cluster-filter').value;
    card.click();
    const after = document.getElementById('adintel-cluster-filter').value;
    return { before, after, changed: before !== after };
  });
  console.log('cluster-card click filter result:', JSON.stringify(clickResult));

  // 4) search a record_id that is NOT in the embedded 300 (try a low-activity one)
  const searchNotFound = await page.evaluate(() => {
    const sel = document.getElementById('adintel-ad-selector');
    sel.value = 'h_000c73d78bf8e1a57d46';  // record_id not in 300
    sel.dispatchEvent(new Event('input', { bubbles: true }));
    const results = document.getElementById('adintel-ad-results');
    return { innerHTML: results?.innerHTML?.slice(0,300), childCount: results?.childElementCount };
  });
  console.log('search-not-embedded result:', JSON.stringify(searchNotFound));

  // 5) check for download links
  const downloadLinks = await page.evaluate(() => {
    const links = Array.from(document.querySelectorAll('a[href]'));
    return links
      .filter(a => /\.jsonl|solarize_summary|solarize_per_ad|\.json(\?|$)/.test(a.href))
      .map(a => ({ href: a.href, text: a.textContent.trim().slice(0,80) }));
  });
  console.log('download links:', JSON.stringify(downloadLinks));

  // 6) check for any link/section explaining Wilson/Cohen's h/BH FDR/why k=5
  const methodologyMentions = await page.evaluate(() => {
    const body = document.body.innerText.toLowerCase();
    return {
      why_wilson: body.includes('why wilson') || body.includes('wilson over wald') || body.includes('wilson score'),
      why_cohens_h: body.includes('why cohen') || body.includes("cohen's h over"),
      why_bh_fdr: body.includes('why benjamini') || body.includes('bh over bonferroni') || body.includes('benjamini-hochberg over'),
      why_k5: body.includes('why k=5') || body.includes('k=5 was chosen') || body.includes('chose k=5'),
      min_support_why: body.includes('why min-support') || body.includes('min-support threshold of 5') || body.includes('threshold of 5'),
      four_part_criterion: body.includes('four-part') || body.includes('four part criterion'),
      red_phase: body.includes('red phase') || body.includes('red-phase') || body.includes('solarize red'),
      green_phase: body.includes('green phase') || body.includes('green-phase') || body.includes('solarize green'),
      audit_methodology: body.includes('audit methodology') || body.includes('solarize audit'),
      verification_evidence: body.includes('verification evidence') || body.includes('screenshot'),
      cluster_quality_metrics: body.includes('cluster_quality_metrics') || body.includes('cluster quality metrics')
    };
  });
  console.log('methodology mentions:', JSON.stringify(methodologyMentions, null, 2));

  // 7) check outliers-section → clustering-section cross-links
  const crossLinks = await page.evaluate(() => {
    const outliersSection = document.getElementById('adintel-outliers');
    const clusteringSection = document.getElementById('adintel-clustering');
    if (!outliersSection || !clusteringSection) return { outliersExists: !!outliersSection, clusteringExists: !!clusteringSection };
    const outlierAnchors = outliersSection.querySelectorAll('a[href]');
    const linksToCluster = [];
    outlierAnchors.forEach(a => {
      const href = a.getAttribute('href');
      if (href && (href.includes('adintel-ad=') || href.includes('#adintel-clustering'))) {
        linksToCluster.push({ href, text: a.textContent.trim().slice(0,80) });
      }
    });
    const clusteringAnchors = clusteringSection.querySelectorAll('a[href]');
    const linksToOutliers = [];
    clusteringAnchors.forEach(a => {
      const href = a.getAttribute('href');
      if (href && (href.includes('#adintel-outliers'))) {
        linksToOutliers.push({ href, text: a.textContent.trim().slice(0,80) });
      }
    });
    return { outliers_to_cluster: linksToCluster, cluster_to_outliers: linksToOutliers };
  });
  console.log('cross-links:', JSON.stringify(crossLinks, null, 2));

  // 8) check page errors
  console.log('page errors:', errors.slice(0,10).join('\n') || 'none');

  await browser.close();
})();
