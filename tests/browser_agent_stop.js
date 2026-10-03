async page => {
  // Only the isolated fixture may simulate a stop and a new user instruction
  if (await page.locator('h1').textContent() !== 'Agent progress test') {
    throw Error('This test must not run against a user Studio session');
  }
  const check = (value, message) => { if (!value) throw Error(message); };
  await page.reload();
  await page.waitForFunction(() => !!globalThis.CFDAgent);
  await page.evaluate(() => CFDAgentActivity.refresh());
  check(!await page.locator('#agentBanner').isVisible(), 'Idle banner visible');
  check(await page.locator('#agentDock,#agentSettingsRow,#agentExecute').count() === 0, 'Manual controls remain');
  await page.keyboard.press('Alt+Shift+A');
  check(!await page.locator('#agentBanner').isVisible(), 'Human keyboard toggle activated UI');
  const activation = await page.evaluate(() => CFDAgent.activate({name:'Test',task:'Isolated lifecycle test'}));
  check(activation.status === 'active', 'Agent activation failed');
  await page.locator('#agentBannerStop').waitFor({state:'visible'});
  await page.evaluate(() => {
    globalThis.fixturePause = null;
    addEventListener('cfd-agent-pause', event => { globalThis.fixturePause = event.detail; });
  });
  await page.locator('#agentBannerStop').click();
  await page.locator('#agentBannerStop').waitFor({state:'hidden'});
  await page.waitForFunction(() => CFDAgent.state().progress.state.stop_revision > 0);
  const stopped = await page.evaluate(async () => ({
    signal:globalThis.fixturePause?.type,
    paused:CFDAgent.status().paused,
    command:(await CFDAgent.run('cfd.open')).error,
    activation:(await CFDAgent.activate({task:'Unauthorized fixture retry'})).error
  }));
  check(stopped.signal === 'pause' && stopped.paused, 'Stop signal missing');
  check(stopped.command === 'PAUSED' && stopped.activation === 'PAUSED', 'Stopped commands accepted');
  await page.reload();
  await page.waitForFunction(() => globalThis.CFDAgent?.status().paused);
  check(!await page.locator('#agentBanner').isVisible(), 'Reload exposed stopped UI');
  const resumed = await page.evaluate(() => CFDAgent.activate({
    name:'Test',task:'Fixture continuation',
    afterStop:CFDAgent.state().progress.state.stop_revision,
    userRequest:'Isolated test simulates a new explicit user instruction'
  }));
  check(resumed.status === 'active', 'New instruction activation failed');
  await page.locator('#agentBannerStop').waitFor({state:'visible'});
  await page.evaluate(() => CFDAgent.finish());
  await page.locator('#agentBannerStop').waitFor({state:'hidden'});
  const inactive = await page.evaluate(async () => (await CFDAgent.run('cfd.open')).error);
  check(inactive === 'AGENT_INACTIVE', 'Finished session accepted commands');
  return {activation:true,stop:stopped,reloadPreservedPause:true,completionHidden:true};
};
