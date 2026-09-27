// 전용 Playwright 세션에서만 실행한다. 새 UX 테스트 실험 외 기존 입력은 수정하지 않는다.
async (page) => {
  const origin = await page.evaluate(() => location.origin);
  if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(origin))
    throw Error("Local review server required");
  const checks = [],
    errors = [];
  const check = (ok, label) => {
    if (!ok) throw Error(label);
    checks.push(label);
  };
  const onError = (error) => errors.push(error.message);
  page.on("pageerror", onError);
  // CLI는 네이티브 모달에서 명령을 중단한다. 전용 시험 페이지에서는 수락 경로를 고정한다.
  await page.addInitScript(() => {
    window.confirm = () => true;
    window.addEventListener(
      "beforeunload",
      (e) => e.stopImmediatePropagation(),
      true,
    );
  });
  const post = async (url, data) => {
    const response = await page.request.post(origin + url, { data });
    const value = await response.json();
    if (!response.ok() || value.ok === false)
      throw Error(JSON.stringify(value));
    return value.result;
  };
  const get = async (url) => (await page.request.get(origin + url)).json();
  const make = async (name, design) => {
    const s = (await post("/api/studies", { name })).id;
    const p = await post("/api/studies/" + s + "/preview", { design });
    await post("/api/studies/" + s + "/commit", {
      design,
      preview_hash: p.preview_hash,
      expected_revision: null,
    });
    return s;
  };
  const a = await make("UX 검토 A " + Date.now(), {
    variable: "porosity",
    method: "manual",
    values: [0.3, 0.6],
    seed: 31,
  });
  const b = await make("UX 검토 B " + Date.now(), {
    variable: "K_porous_m2_s",
    method: "manual",
    values: [0.001, 0.004],
    seed: 73,
  });
  const choose = async (id, variable) => {
    await page.locator("#studies").selectOption(id);
    if (id)
      await page.waitForFunction(
        (v) =>
          document.querySelector("#variable").value === v &&
          !document.querySelector("#preview").disabled,
        variable,
      );
  };
  try {
    await page.goto(origin + "/studies?study=" + a);
    await page.waitForFunction(
      () =>
        document.querySelector("#variable").value === "porosity" &&
        !document.querySelector("#preview").disabled,
    );
    check(
      (await page.locator("#values").inputValue()) === "0.3,0.6",
      "saved design restored",
    );
    check(
      (await page.locator("#seed").inputValue()) === "31",
      "saved seed restored",
    );
    await page.locator("#values").fill("0.31,0.61");
    check(
      await page.locator("#enqueue").isDisabled(),
      "dirty inputs cannot execute old revision",
    );
    await choose(b, "K_porous_m2_s");
    check(
      (await page.locator("#values").inputValue()) === "0.001,0.004",
      "other study has independent input",
    );
    await choose(a, "porosity");
    check(
      (await page.locator("#values").inputValue()) === "0.31,0.61",
      "study draft restored",
    );
    await page.reload();
    await page.waitForFunction(
      () => document.querySelector("#values").value === "0.31,0.61",
    );
    check(
      await page.locator("#enqueue").isDisabled(),
      "reload preserves dirty state",
    );
    await page.locator("#revert").click();
    await page.waitForFunction(
      () => document.querySelector("#values").value === "0.3,0.6",
    );
    check(
      await page.locator("#enqueue").isEnabled(),
      "discard draft restores executable revision",
    );

    let release, entered;
    const started = new Promise((resolve) => (entered = resolve)),
      hold = new Promise((resolve) => (release = resolve));
    const path = "**/api/studies/" + a + "/preview";
    await page.route(path, async (route) => {
      entered();
      await hold;
      await route.continue();
    });
    await page.locator("#preview").click();
    await started;
    check(
      await page.locator("#values").isDisabled(),
      "preview request locks input",
    );
    await choose(b, "K_porous_m2_s");
    release();
    await page.waitForResponse((r) => r.url().endsWith("/" + a + "/preview"));
    await page.unroute(path);
    check(
      await page.locator("#commit").isDisabled(),
      "late preview cannot authorize other study",
    );
    check(
      (await page.locator("#variable").inputValue()) === "K_porous_m2_s",
      "late response does not overwrite selection",
    );
    await choose("");
    check(
      (await page.locator("#enqueue").isDisabled()) &&
        (await page.locator("#export").isDisabled()),
      "empty selection disables actions",
    );
    check(
      (await page.locator("#candidates tr").count()) === 0 &&
        (await page.locator("#attempts tr").count()) === 0,
      "empty selection clears prior data",
    );

    await choose(a, "porosity");
    await page.locator("#values").fill("0.29,0.59");
    const latest = await get("/api/studies/" + a);
    const design = {
      variable: "porosity",
      method: "manual",
      values: [0.32, 0.62],
      seed: 31,
    };
    const p = await post("/api/studies/" + a + "/preview", { design });
    await post("/api/studies/" + a + "/commit", {
      design,
      preview_hash: p.preview_hash,
      expected_revision: latest.current_revision,
    });
    await page.waitForFunction(() =>
      document.querySelector("#msg").textContent.includes("다른 창"),
    );
    check(
      (await page.locator("#values").inputValue()) === "0.29,0.59",
      "external revision preserves edits",
    );
    await page.locator("#revert").click();
    await page.waitForFunction(
      () => document.querySelector("#values").value === "0.32,0.62",
    );
    check(
      await page.locator("#enqueue").isEnabled(),
      "external revision conflict can recover",
    );

    await page.locator("#values").fill("0.33,0.63");
    await page.locator("#preview").click();
    await page.locator("#commit").waitFor({ state: "visible" });
    await page.waitForFunction(
      () => !document.querySelector("#commit").disabled,
    );
    await page.locator("#commit").click();
    await page.waitForFunction(
      () => !document.querySelector("#enqueue").disabled,
    );
    await page.reload();
    await page.waitForFunction(
      () => !document.querySelector("#enqueue").disabled,
    );
    check(
      (await page.locator("#values").inputValue()) === "0.33,0.63",
      "committed values restored without stale draft",
    );
    check(
      (await page.locator("#dirty").textContent()) === "",
      "successful commit clears draft",
    );

    await page.locator("#enqueue").click();
    await page.waitForFunction(
      () =>
        document.querySelectorAll("#attempts tr").length === 3 &&
        [...document.querySelectorAll("#attempts tr")].every((r) =>
          r.textContent.includes("통과"),
        ),
      null,
      { timeout: 120000 },
    );
    check(
      (await get("/api/studies/" + a)).attempts.length === 3,
      "three CFD cases completed from UI",
    );
    await page.locator("#export").click();
    await page.locator("#download").waitFor({ state: "visible" });
    const link = await page.locator("#download").getAttribute("href");
    const download = await page.request.get(origin + link);
    check(
      download.ok() && (await download.body()).byteLength > 1000,
      "result package downloadable",
    );
    await page.setViewportSize({ width: 390, height: 844 });
    check(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      "mobile page has no horizontal overflow",
    );
    await page.locator("#chart").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: "output/playwright/study-review-mobile.png",
    });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({
      path: "output/playwright/study-review-desktop.png",
    });
    check(errors.length === 0, "no browser runtime errors");
    return { checks, study: a, comparison: b, package: link };
  } finally {
    page.off("pageerror", onError);
  }
}
