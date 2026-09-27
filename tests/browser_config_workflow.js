// tests/serve_config_review.py 전용. 운영 프로젝트나 실제 솔버에는 접근하지 않는다.
async (page) => {
  const checks = [], errors = [];
  const check = (ok, label) => { if (!ok) throw Error(label); checks.push(label); };
  const onError = error => errors.push(error.message);
  page.on('pageerror', onError);
  const origin = await page.evaluate(() => location.origin);
  const name = '설정 UI 검사 ' + Date.now();
  let release;
  try {
    await page.reload();
    await page.waitForFunction(() => typeof CFG !== 'undefined' && CFG?.tank);
    await page.setViewportSize({width: 1440, height: 1000});
    await page.getByRole('button', {name: '새 설정 만들기', exact: true}).click();
    const input = key => page.locator('#cbForm input[data-g="run"][data-k="'+key+'"]');
    check(await input('write_interval_s').inputValue() === '0.5', 'restart snapshot interval is editable from selected preset');
    await input('end_time_s').fill('32.5');
    await page.locator('#cbType').selectOption('grain_silo');
    await page.locator('#cbSiloEnd').fill('37'); await page.locator('#cbSiloWrite').fill('3');
    await page.locator('#cbSiloSolver').selectOption('pimpleFoam');
    await page.locator('#cbSiloEnd').fill('1.75'); await page.locator('#cbSiloWrite').fill('0.05');
    await page.locator('#cbSiloDt').fill('0.002');
    await page.locator('#cbSiloSolver').selectOption('simpleFoam');
    check(await page.locator('#cbSiloEnd').inputValue() === '37', 'steady iteration target survives solver switch');
    await page.locator('#cbType').selectOption('immersion');
    check(await input('end_time_s').inputValue() === '32.5', 'immersion draft survives analysis switch');
    await page.locator('#cbType').selectOption('grain_silo');
    check(await page.locator('#cbSiloEnd').inputValue() === '37', 'silo draft survives analysis switch');
    await page.locator('#cbSiloSolver').selectOption('pimpleFoam');
    check(await page.locator('#cbSiloEnd').inputValue() === '1.75'
      && await page.locator('#cbSiloDt').inputValue() === '0.002', 'transient duration and timestep restored independently');
    check(await page.locator('#cbSiloEndUnit').textContent() === 's'
      && !(await page.locator('#cbSiloPlayback').isVisible()), 'physical seconds and iteration playback are separate');
    await page.locator('#cbName').fill(name);
    await page.locator('#cbSiloCells').fill('1000.5');
    let requests = 0;
    const counter = request => { if (request.url().endsWith('/api/config-save')) requests++; };
    page.on('request', counter);
    await page.locator('#cbSave').click();
    check(requests === 0 && await page.locator('#cbBg').isVisible(), 'fractional cell count rejected before request');
    await page.locator('#cbSiloCells').fill('1000'); await page.locator('#cbSiloDarcy').fill('');
    await page.locator('#cbSave').click();
    check(requests === 0, 'blank numeric entry is not silently converted to zero');
    await page.locator('#cbSiloDarcy').fill('0');
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**/api/config-save', async route => { await gate; await route.continue(); });
    await page.locator('#cbSave').click();
    await page.waitForFunction(() => CBSAVING);
    check(await page.locator('#cbType').isDisabled() && await page.locator('#cbSiloEnd').isDisabled(), 'save locks the input snapshot');
    await page.evaluate(() => { saveCB(); closeCB(); });
    check(requests === 1 && await page.locator('#cbBg').isVisible(), 'repeated save and close cannot interrupt pending request');
    release(); await page.waitForFunction(() => !CBSAVING);
    await page.unroute('**/api/config-save');
    check(!(await page.locator('#cbBg').isVisible()), 'successful save closes dialog');
    const saved = await (await page.request.get(origin+'/api/config?saved='+encodeURIComponent(name))).json();
    check(saved.config.run.time_basis === 'physical_time' && saved.config.run.end_time_s === 1.75
      && saved.config.run.time_step_s === .002 && saved.config.mesh.target_cells === 1000,
      'JSON round-trip preserves exact entered values and time basis');
    await page.getByRole('button', {name: '새 설정 만들기', exact: true}).click();
    await page.locator('#cbName').fill(name); await page.locator('#cbSiloEnd').fill('2.5');
    const conflict = page.waitForResponse(r => r.url().endsWith('/api/config-save'));
    await page.locator('#cbSave').click(); check((await conflict).status() === 409, 'duplicate preset rejected with conflict response');
    await page.waitForFunction(() => !CBSAVING);
    const unchanged = await (await page.request.get(origin+'/api/config?saved='+encodeURIComponent(name))).json();
    check(unchanged.config.run.end_time_s === 1.75 && await page.locator('#cbSiloEnd').inputValue() === '2.5', 'conflict preserves original file and unsaved draft');
    await page.route('**/api/config-save', route => route.abort('failed'));
    await page.locator('#cbName').fill(name+' 연결 시험'); await page.locator('#cbSave').click();
    await page.waitForFunction(() => !CBSAVING);
    check(await page.locator('#cbSave').isEnabled() && await page.locator('#cbSiloEnd').inputValue() === '2.5', 'connection failure restores editable draft');
    await page.unroute('**/api/config-save');
    page.off('request', counter);
    await page.waitForFunction(() => document.querySelectorAll('#toasts .toast').length === 0);
    for (const [mode, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({width, height});
      await page.locator('#cbSave').scrollIntoViewIfNeeded();
      const geometry = await page.locator('#cbBg .mbox').evaluate(el => {
        const r = el.getBoundingClientRect();
        return {left: r.left, right: r.right, width: innerWidth, overflow: el.scrollWidth > el.clientWidth + 1};
      });
      check(geometry.left >= 0 && geometry.right <= geometry.width + 1 && !geometry.overflow, mode+' settings dialog fits viewport');
      await page.screenshot({path: 'output/playwright/config-review-'+mode+'.png'});
    }
    check(!errors.length, 'no uncaught browser script errors');
    return {checks, screenshotPrefix: 'output/playwright/config-review-', errors};
  } finally {
    if (release) release();
    await page.unroute('**/api/config-save');
    page.off('pageerror', onError);
  }
}
