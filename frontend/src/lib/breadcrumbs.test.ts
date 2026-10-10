import { describe, expect, it } from "vitest";
import { hasBreadcrumbs, parsePathname } from "@/lib/breadcrumbs";

describe("breadcrumb path parsing", () => {
  it("returns nothing outside the workspace", () => {
    expect(parsePathname("/login")).toEqual([]);
    expect(parsePathname("/")).toEqual([]);
    expect(hasBreadcrumbs("/login")).toBe(false);
  });

  it("treats the dashboard as the workspace root (no crumbs)", () => {
    expect(parsePathname("/app")).toEqual([{ label: "Workspace", to: "/app" }]);
    expect(hasBreadcrumbs("/app")).toBe(false);
  });

  it("marks the final segment as the current (non-clickable) page", () => {
    expect(parsePathname("/app/cases")).toEqual([
      { label: "Workspace", to: "/app" },
      { label: "Cases", to: undefined },
    ]);
    expect(hasBreadcrumbs("/app/cases")).toBe(true);
  });

  it("links every intermediate segment", () => {
    expect(parsePathname("/app/cases/abc/entities")).toEqual([
      { label: "Workspace", to: "/app" },
      { label: "Cases", to: "/app/cases" },
      { label: "Abc", to: "/app/cases/abc" },
      { label: "Entities", to: undefined },
    ]);
  });

  it("uses friendly labels for known segments", () => {
    expect(parsePathname("/app/cases/x/reports").at(-1)).toEqual({
      label: "Reports",
      to: undefined,
    });
    expect(parsePathname("/app/cases/x/iot").at(-1)).toEqual({
      label: "IoT Devices",
      to: undefined,
    });
    expect(parsePathname("/app/cases/x/timeline").at(-1)).toEqual({
      label: "Timeline",
      to: undefined,
    });
  });
});
