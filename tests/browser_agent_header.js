async page => {
  // Read the active Studio only; never change projects, settings or queue state
  const result = await page.evaluate(() => {
    const state = CFDAgent.observe();
    const controls = ['mCFD', 'mViz', 'settingsBtn', 'infoBtn', 'agentBannerStop'].map(id => {
      const element = document.getElementById(id);
      if (!element) return {id, accessible: false};
      const rect = element.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
      return {id, accessible: rect.width > 0 && rect.height > 0 &&
        (hit === element || element.contains(hit))};
    });
    return {dialog: state.dialog, errors: state.errors, progress: state.progress, controls};
  });
  if (result.dialog) throw Error('Close the dialog before checking the application header');
  if (result.errors.length) throw Error('Studio reported interface errors');
  if (!result.progress?.available || !result.progress.displayed) throw Error('Visible progress receipt missing');
  for (const control of result.controls) {
    if (!control.accessible) throw Error('Header control is covered: ' + control.id);
  }
  return result;
};
