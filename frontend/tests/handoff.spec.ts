import { test, expect } from "@playwright/test";

test("conflicting evidence dispatches comparison and stays blocked", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill("admin@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.E2E_PASSWORD ?? "Testing-password-42");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Every handoff, accounted for." }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Handoff queue", exact: true }).click();
  await page.locator(".case-link").filter({ hasText: "SO-1042" }).click();
  await page.getByRole("button", { name: "Run investigation" }).click();
  await expect(
    page.locator(".case-summary").getByText("WAITING", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    page
      .locator(".requirement")
      .filter({ hasText: "Consistent payment terms" })
      .getByText("CONFLICTING", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Agent activity" }).click();
  await expect(
    page
      .locator(".timeline strong")
      .filter({ hasText: "Conflict Agent" })
      .first(),
  ).toBeVisible();
  await page.screenshot({
    path:
      (process.env.QA_SCREENSHOT_DIR ?? "test-results") +
      "/case-conflict-graph.png",
    fullPage: true,
  });
});

test("login, investigate, clarify, approve, verify and refresh", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill("admin@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.E2E_PASSWORD ?? "Testing-password-42");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Every handoff, accounted for." }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Handoff queue", exact: true }).click();
  await page.getByRole("button", { name: "New handoff" }).click();
  await page
    .getByLabel("Case conditions (JSON object)")
    .fill('{"discount_requires_approval":"no"}');
  const businessKey = "E2E-" + Date.now();
  await page.getByLabel("Business ID").fill(businessKey);
  await page
    .getByLabel("Title", { exact: true })
    .fill("End-to-end clarification case");
  await page.getByRole("button", { name: "Create case", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "End-to-end clarification case" }),
  ).toBeVisible();
  // A real EventSource must receive a backend routing event.
  await page.evaluate(() => {
    (window as unknown as { receivedEvent: boolean }).receivedEvent = false;
    const id = location.pathname.split("/").at(-1);
    const events = new EventSource("/api/cases/" + id + "/events");
    events.onmessage = (e) => {
      const event = JSON.parse(e.data);
      if (event.kind === "routing") {
        (window as unknown as { receivedEvent: boolean }).receivedEvent = true;
        events.close();
      }
    };
  });
  await page.getByRole("button", { name: "Run investigation" }).click();
  await expect(
    page.locator(".case-summary").getByText("WAITING", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await expect
    .poll(() =>
      page.evaluate(
        () => (window as unknown as { receivedEvent: boolean }).receivedEvent,
      ),
    )
    .toBe(true);
  await page.reload();
  await expect(
    page.locator(".case-summary").getByText("WAITING", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Repair plan" }).click();
  await page.getByRole("button", { name: "Record clarification" }).click();
  for (const [key, value] of Object.entries({
    purchase_order: "PO-E2E",
    quotation: "QT-E2E",
    account: "AC-E2E",
    terms: "30 days",
    tax: "TAX-E2E",
  }))
    await page.getByLabel(key + " (leave blank if unresolved)").fill(value);
  await page
    .getByLabel("Reason / source of clarification")
    .fill("Confirmed against original customer order documents");
  await page.getByRole("button", { name: "Submit clarification" }).click();
  await expect(
    page.getByRole("button", { name: "Approve action" }),
  ).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "Approve action" }).click();
  await page
    .getByLabel("Reason / source of clarification")
    .fill("Reviewer checked original sources and accepts the candidate facts");
  await page.getByRole("button", { name: "Confirm approval" }).click();
  await expect(
    page.locator(".case-summary").getByText("READY", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await page.reload();
  await expect(
    page.locator(".case-summary").getByText("READY", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Agent activity" }).click();
  await expect(page.getByLabel("Observed agent routing graph")).toBeVisible();
  for (const tab of [
    "Requirements",
    "Evidence",
    "Repair plan",
    "Agent activity",
    "History",
  ]) {
    await page.getByRole("tab", { name: tab, exact: true }).click();
    await page.screenshot({
      path:
        (process.env.QA_SCREENSHOT_DIR ?? "test-results") +
        "/case-" +
        tab.replaceAll(" ", "-") +
        ".png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      )
      .toBe(true);
    await page.screenshot({
      path:
        (process.env.QA_SCREENSHOT_DIR ?? "test-results") +
        "/case-mobile-" +
        tab.replaceAll(" ", "-") +
        ".png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 1280, height: 800 });
  }
  expect(errors).toEqual([]);
});

test("primary screens and narrow layout", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill("admin@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.E2E_PASSWORD ?? "Testing-password-42");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Every handoff, accounted for." }),
  ).toBeVisible();
  for (const route of [
    "/",
    "/cases",
    "/actions",
    "/workflows",
    "/audit",
    "/admin",
  ]) {
    await page.goto(route);
    await expect(page.locator("main h1")).toBeVisible();
    await page.screenshot({
      path:
        (process.env.QA_SCREENSHOT_DIR ?? "test-results") +
        "/desktop-" +
        (route.slice(1) || "dashboard") +
        ".png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      )
      .toBe(true);
    await page.screenshot({
      path:
        (process.env.QA_SCREENSHOT_DIR ?? "test-results") +
        "/mobile-" +
        (route.slice(1) || "dashboard") +
        ".png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 1280, height: 800 });
  }
  expect(errors).toEqual([]);
});

test("policy versioning, mobile sign-out and restricted operator intake", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill("admin@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.E2E_PASSWORD ?? "Testing-password-42");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("link", { name: "Workflow studio", exact: true })
    .click();
  await page.getByRole("button", { name: "New workflow" }).click();
  const name = "Audited policy " + Date.now();
  await page.getByLabel("Workflow name").fill(name);
  await page.getByLabel("Source team", { exact: true }).fill("Sales");
  await page.getByLabel("Receiving team").fill("Finance");
  await page.getByLabel("Label", { exact: true }).fill("Purchase order");
  await page.getByRole("button", { name: "Publish approved version" }).click();
  const card = page.locator(".workflow-card").filter({ hasText: name });
  await expect(card).toHaveCount(1);
  await card.getByRole("button", { name: "Create new version" }).click();
  await page.getByLabel("Expected value (optional)").fill("PO-AUDIT");
  await page.getByRole("button", { name: "Publish approved version" }).click();
  await expect(card).toHaveCount(2);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in to your workspace" }),
  ).toBeVisible();
  await page.getByLabel("Email", { exact: true }).fill("operator@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.E2E_PASSWORD ?? "Testing-password-42");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: "Handoff queue", exact: true }).click();
  await page.getByRole("button", { name: "New handoff" }).click();
  await expect(page.getByLabel("Case conditions (JSON object)")).toHaveCount(0);
  await page.getByLabel("Business ID").fill("OPERATOR-" + Date.now());
  await page.getByLabel("Title", { exact: true }).fill("Operator intake");
  await page.getByRole("button", { name: "Create case", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Operator intake" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Edit case conditions" }),
  ).toHaveCount(0);
  // Prove canonical polling continues when the SSE transport is unavailable.
  await page.route("**/events", (route) => route.abort());
  await page.reload();
  await page.getByRole("button", { name: "Run investigation" }).click();
  await expect(
    page.locator(".case-summary").getByText("WAITING", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await page.getByRole("tab", { name: "Agent activity" }).click();
  await expect(
    page.getByText("Live updates reconnecting; periodic refresh is active", {
      exact: true,
    }),
  ).toBeVisible();
});
