// 구조화된 테스트 가정만 사용한다. 실제 저장고 설정·물성값을 수정하지 않는다.
async (page) => {
  const origin = await page.evaluate(() => location.origin),
    checks = [],
    errors = [];
  const check = (ok, label) => {
    if (!ok) throw Error(label);
    checks.push(label);
  };
  const error = (e) => errors.push(e.message);
  page.on("pageerror", error);
  await page.addInitScript(() => {
    window.confirm = () => true;
    window.addEventListener(
      "beforeunload",
      (e) => e.stopImmediatePropagation(),
      true,
    );
  });
  const post = async (url, data) => {
    const r = await page.request.post(origin + url, { data });
    const v = await r.json();
    if (!r.ok() || v.ok === false) throw Error(JSON.stringify(v));
    return v.result;
  };
  const a = (await post("/api/studies", { name: "UX 설계 A " + Date.now() }))
      .id,
    b = (await post("/api/studies", { name: "UX 설계 B " + Date.now() })).id;
  const fixture = "tests/fixtures/research_design_valid.json",
    invalid = "tests/fixtures/research_design_invalid.json";
  const choose = async (id) => {
    await page.locator("#study").selectOption(id);
    await page.waitForFunction(
      () => !document.querySelector("#common").disabled,
    );
  };
  try {
    await page.goto(origin + "/studies/design?study=" + a);
    await page.waitForFunction(
      () => !document.querySelector("#common").disabled,
    );
    await page.locator("#import").setInputFiles(fixture);
    await page.waitForFunction(() =>
      document.querySelector("#common").value.includes("length_m"),
    );
    const common = await page.locator("#common").inputValue();
    await page.locator("#preview").click();
    await page.waitForFunction(
      () => document.querySelectorAll("#candidates tr").length === 2,
    );
    check(
      await page.locator("#commit").isEnabled(),
      "valid imported design generates candidates",
    );
    await page.locator("#candidates tr").last().focus();
    await page.keyboard.press("Enter");
    check(
      (await page
        .locator("#candidates tr")
        .last()
        .getAttribute("aria-selected")) === "true",
      "candidate selection works with keyboard",
    );
    await page.locator("#common").fill("{");
    check(
      (await page.locator("#candidates tr").count()) === 0 &&
        (await page.locator("#selected").textContent()) === "",
      "editing clears stale preview",
    );
    await choose(b);
    await choose(a);
    check(
      (await page.locator("#common").inputValue()) === "{",
      "invalid JSON draft preserved across study switch",
    );
    await page.reload();
    await page.waitForFunction(
      () => document.querySelector("#common").value === "{",
    );
    check(
      (await page.locator("#common").inputValue()) === "{",
      "invalid JSON draft preserved on reload",
    );
    await page.locator("#common").fill(common);
    const before = await page
      .locator('[aria-label="적재 배치 value"]')
      .inputValue();
    await page.locator("#import").setInputFiles(invalid);
    await page.waitForFunction(
      () => document.querySelector("#status").textContent.length > 0,
    );
    check(
      (await page.locator('[aria-label="적재 배치 value"]').inputValue()) ===
        before && (await page.locator("#common").inputValue()) === common,
      "malformed import does not partly replace fields",
    );
    await page.locator("#preview").click();
    await page.waitForFunction(
      () => !document.querySelector("#commit").disabled,
    );
    await page.locator("#commit").click();
    await page.waitForFunction(() =>
      document.querySelector("#status").textContent.includes("저장 완료"),
    );
    await page.reload();
    await page.waitForFunction(
      () => document.querySelectorAll("#candidates tr").length === 2,
    );
    check(
      await page.locator("#commit").isDisabled(),
      "saved preview restored read-only",
    );
    const pixels = await page.evaluate(() => {
      const c = document.querySelector("#scene canvas"),
        g = c.getContext("webgl2"),
        p = new Uint8Array(c.width * c.height * 4);
      g.readPixels(0, 0, c.width, c.height, g.RGBA, g.UNSIGNED_BYTE, p);
      return new Set(
        Array.from({ length: Math.floor(p.length / 64) }, (_, i) =>
          p.slice(i * 64, i * 64 + 3).join(","),
        ),
      ).size;
    });
    check(pixels > 10, "3D geometry canvas is nonblank");
    const c = page.locator("#scene canvas");
    await c.scrollIntoViewIfNeeded();
    const first = await c.screenshot(),
      box = await c.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2);
    await page.mouse.up();
    const next = await c.screenshot();
    check(!first.equals(next), "3D rotation changes rendered geometry");
    await page.screenshot({
      path: "output/playwright/design-review-desktop.png",
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await c.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: "output/playwright/design-review-mobile.png",
    });
    check(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      "designer mobile has no page overflow",
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    const result = await page.request.get(origin + "/api/studies/" + a);
    const d = await result.json();
    const refused = await page.request.post(
      origin + "/api/studies/" + a + "/enqueue",
      {
        data: {
          cases: d.cases.map((c) => c.id),
          request_id: "design-block-" + Date.now(),
        },
      },
    );
    check(refused.status() === 400, "geometry cannot execute as fake ClO2");
    check(errors.length === 0, "designer no browser runtime errors");
    return { checks, study: a, other: b, pixels };
  } finally {
    page.off("pageerror", error);
  }
}
