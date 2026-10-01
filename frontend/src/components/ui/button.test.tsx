import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Button } from "./button";
test("disabled action cannot invoke handler", () => {
  const fn = vi.fn();
  render(
    <Button disabled onClick={fn}>
      Approve
    </Button>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Approve" }));
  expect(fn).not.toHaveBeenCalled();
});
test("asChild renders an accessible link without nested button", () => {
  render(
    <Button asChild>
      <a href="/cases">Open queue</a>
    </Button>,
  );
  expect(screen.getByRole("link", { name: "Open queue" })).toHaveAttribute(
    "href",
    "/cases",
  );
  expect(screen.queryByRole("button", { name: "Open queue" })).toBeNull();
});
