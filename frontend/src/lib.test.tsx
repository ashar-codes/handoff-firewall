import { afterEach, expect, test, vi } from "vitest";
import { api } from "./lib";
afterEach(() => vi.restoreAllMocks());
test("API sends CSRF token and cookie credentials", async () => {
  document.cookie = "hf_csrf=verified-token";
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response("{}", { status: 200 }));
  await api("/cases", { method: "POST", body: "{}" });
  expect(fetch).toHaveBeenCalledWith(
    "/api/cases",
    expect.objectContaining({
      credentials: "include",
      headers: expect.objectContaining({
        "X-CSRF-Token": "verified-token",
        "Content-Type": "application/json",
      }),
    }),
  );
});
test("API exposes safe server rejection", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response('{"detail":"Approval view is stale"}', { status: 409 }),
  );
  await expect(api("/actions/a/decision")).rejects.toThrow(
    "Approval view is stale",
  );
});
