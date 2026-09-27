// 실제 소규모 검증 결과를 읽기만 한다. 계산 시작·프로젝트 삭제는 수행하지 않는다.
async page => {
  const checks=[],errors=[],error=e=>errors.push(e.message);
  const check=(ok,label)=>{if(!ok)throw Error(label);checks.push(label);};
  page.on('pageerror',error);
  try {
    await page.setViewportSize({width:1440,height:1000});
    await page.waitForFunction(()=>typeof FRAMES!=='undefined'&&FRAMES.length===11&&typeof TRACERMAP!=='undefined'&&TRACERMAP.concentration[0]);
    check(await page.evaluate(()=>MODE==='viz'&&FRAMES[0].t===0&&FRAMES[10].t===1),'result opens from zero with all 11 frames');
    await page.locator('#speed').selectOption('8');
    await page.locator('#tbar').fill('8');
    await page.locator('#play').click();
    await page.waitForFunction(()=>PLAYENDED&&!PLAYBUFFERING&&!playing,{},{timeout:10000});
    check(await page.evaluate(()=>clock===1),'8x playback reaches end without infinite buffering');
    check((await page.locator('#play').getAttribute('title')).includes('처음'),'end button offers replay');
    await page.locator('#speed').selectOption('0.1');
    await page.locator('#play').click();
    await page.waitForFunction(()=>playing&&clock>0&&clock<.8);
    await page.locator('#play').click();
    const paused=await page.evaluate(()=>({clock,playing}));
    check(!paused.playing&&paused.clock<1,'replay starts from beginning and can pause');
    await page.locator('#mCFD').click();
    await page.locator('#mViz').click();
    check(await page.evaluate(()=>MODE==='viz'&&isTracerConfig(VIZCFG)&&FRAMES.length===11),'CFD and Viewer round trip retains selected data');
    const pixels=await page.evaluate(()=>{
      const p=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);
      gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,p);
      return new Set(Array.from({length:Math.floor(p.length/64)},(_,i)=>p.slice(i*64,i*64+3).join(','))).size;
    });
    check(pixels>10,'concentration WebGL canvas is nonblank');
    await page.screenshot({path:'output/playwright/viewer-review-desktop.png'});
    await page.setViewportSize({width:390,height:844});
    check(await page.locator('#studiesLink').isVisible(),'research navigation remains visible on mobile');
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile Viewer has no horizontal page overflow');
    await page.screenshot({path:'output/playwright/viewer-review-mobile.png'});
    check(errors.length===0,'Viewer has no browser runtime errors');
    return {checks,pixels,paused};
  } finally {page.off('pageerror',error);await page.setViewportSize({width:1440,height:1000});}
}
