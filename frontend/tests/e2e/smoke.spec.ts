import { expect, test } from "@playwright/test";

// Requires the ground station running with the built app (see frontend/README.md).
// The attack-lab test needs the server started with PIXELPROOF_LAB_MODE=1 (scripts/quick_demo.py does this).
test("overview loads with the hero and live figures", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Prove where every pixel came from/i })).toBeVisible();
  await expect(page.getByText(/nothing here is typed by hand/i)).toBeVisible();
});

test("the Analyse page asks the two questions", async ({ page }) => {
  await page.goto("/#/analyse");
  await expect(page.getByRole("heading", { name: /Analyse a patch/i })).toBeVisible();
  await expect(page.getByText(/is the provenance intact/i)).toBeVisible();
});

test("navigates to the jury attack guide", async ({ page }) => {
  await page.goto("/#/attacks");
  await expect(page.getByRole("heading", { name: /^Attack guide$/i })).toBeVisible();
  await expect(page.getByText(/never launches anything/i)).toBeVisible();
});

test("every page in the navigation opens without an error", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  for (const [hash, heading] of [
    ["#/station", /Satellite and ground station/i],
    ["#/audit", /Audit log/i],
    ["#/about", /About PixelProof/i],
    ["#/results", /Results/i],
    ["#/provenance", /Provenance timeline/i],
    ["#/live", /Live link/i],
  ] as const) {
    await page.goto(`/${hash}`);
    await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test("the attack lab runs a real attack and shows the result", async ({ page }) => {
  await page.goto("/#/lab");
  const run = page.getByRole("button", { name: "Run Image tampering after signing" });
  await expect(run).toBeVisible();
  if (await run.isDisabled()) test.skip(true, "lab mode is off on this server (start it with PIXELPROOF_LAB_MODE=1)");
  await run.click();
  await expect(page.getByText("The attack was stopped")).toBeVisible({ timeout: 30_000 });
});
