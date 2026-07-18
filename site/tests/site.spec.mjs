import { expect, test } from "@playwright/test";

const routes = [
  "/",
  "/console/",
  "/developers/",
  "/chat/",
  "/providers/",
  "/network/",
  "/docs/",
  "/status/",
  "/investors/",
  "/about/",
  "/contact/",
  "/privacy/",
  "/terms/",
  "/litepaper/",
  "/whitepaper/",
];

for (const route of routes) {
  test(`${route} renders with one accessible page heading`, async ({ page }) => {
    const errors = [];
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    const response = await page.goto(route, { waitUntil: "domcontentloaded" });
    expect(response?.status()).toBe(200);
    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.locator("h1")).not.toBeEmpty();
    expect(await page.locator("main").count()).toBe(1);
    expect(errors).toEqual([]);
  });
}

test("homepage communicates product, proof, and honest status", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Hardware that/i }),
  ).toBeVisible();
  await expect(page.getByText(/Phase 0 architecture pivot/i)).toBeVisible();
  await expect(page.getByText(/Provider Agent/i).first()).toBeVisible();
  await expect(page.getByRole("link", { name: /Rent compute/i }).first()).toBeVisible();
  await expect(page.getByText("95%", { exact: true })).toBeVisible();
  await expect(page.getByText("ABA", { exact: true }).first()).toBeVisible();

  const fill = await page
    .getByRole("link", { name: /Rent compute/i })
    .first()
    .evaluate((element) => getComputedStyle(element).backgroundImage);
  expect(fill).toContain("gradient");
  expect(fill).toContain("11, 92, 253");
});

test("machine-readable status matches site claims", async ({ request }) => {
  const response = await request.get("/status/manifest.json");
  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  expect(data.phase).toBe("Phase 0");
  expect(data.surfaces.website.mode).toBe("live");
  expect(data.surfaces.api.mode).toBe("in_development");
  expect(data.surfaces.chat.mode).toBe("planned");
});

test("navigation and layout work on mobile", async ({ page }, testInfo) => {
  test.skip(!testInfo.project.name.includes("mobile"), "mobile project only");
  await page.goto("/");
  const burger = page.locator("#hbtn");
  await expect(burger).toHaveAttribute("aria-label", "Open menu");
  await burger.click();
  await expect(burger).toHaveAttribute("aria-expanded", "true");
  await page.getByRole("button", { name: /Products/ }).click();
  await expect(page.getByRole("link", { name: "Console" }).first()).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});

test("all images and form controls have accessible names", async ({ page }) => {
  await page.goto("/");
  const unnamedImages = await page.locator("img:not([alt])").count();
  expect(unnamedImages).toBe(0);
  const email = page.getByRole("textbox", { name: "Email address" });
  await expect(email).toBeVisible();
  await expect(page.getByRole("button", { name: "Join the list" })).toBeVisible();
});

test("product nav links point at the real subdomain, not a duplicate path", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Console" }).first()).toHaveAttribute(
    "href",
    "https://console.abakos.ai/",
  );
  await expect(page.getByRole("link", { name: "Chat" }).first()).toHaveAttribute(
    "href",
    "https://chat.abakos.ai/",
  );
  await expect(page.getByRole("link", { name: "Status" }).first()).toHaveAttribute(
    "href",
    "https://status.abakos.ai/",
  );
  // Regression guard: /testnet/ was merged into /status/ and must not exist
  // as a separate, duplicate page or link anywhere.
  const testnetLinks = await page.locator('a[href*="testnet"]').count();
  expect(testnetLinks).toBe(0);
});

test("status page merges the testnet acceptance gate, no separate page", async ({
  page,
  request,
}) => {
  await page.goto("/status/");
  await expect(page.getByRole("heading", { name: /One source of truth/i })).toBeVisible();
  await expect(page.getByText("Public testnet acceptance gate")).toBeVisible();
  await expect(page.getByText("Seed nodes", { exact: true })).toBeVisible();
  const response = await request.get("/testnet/");
  expect(response.status()).toBeGreaterThanOrEqual(400);
});

test("all generated internal links resolve", async ({ page, request }) => {
  const links = new Set();
  for (const route of routes) {
    await page.goto(route, { waitUntil: "domcontentloaded" });
    const hrefs = await page.locator('a[href^="/"]').evaluateAll((anchors) =>
      anchors.map((anchor) => anchor.getAttribute("href")),
    );
    hrefs
      .filter((href) => href && !href.startsWith("/api/"))
      .forEach((href) => links.add(href.split("#")[0]));
  }
  for (const href of links) {
    const response = await request.get(href);
    expect(response.status(), `broken internal link: ${href}`).toBeLessThan(400);
  }
});
