import { describe, expect, it } from "vitest";
import { ALL_PERMISSIONS, ROLE_PERMISSIONS, hasPermission } from "@/lib/permissions";
import { useAuthStore } from "@/stores/auth";

const GRANTS: Record<string, string[]> = {
  adminSet: ALL_PERMISSIONS,
  viewerSet: ["case.read", "evidence.read", "findings.read"],
};

function resetPermissions(key: keyof typeof GRANTS) {
  useAuthStore.setState({
    status: "authenticated",
    user: null,
    roles: [],
    permissions: [...GRANTS[key]],
    error: null,
  });
}

describe("permission matrix", () => {
  it("mirrors the backend role model (ADMIN owns all permissions)", () => {
    expect(ROLE_PERMISSIONS.ADMIN).toEqual(ALL_PERMISSIONS);
  });

  it("has AUDIT.read granted only to admin and investigator", () => {
    expect(ROLE_PERMISSIONS.ADMIN).toContain("audit.read");
    expect(ROLE_PERMISSIONS.INVESTIGATOR).toContain("audit.read");
    expect(ROLE_PERMISSIONS.ANALYST).not.toContain("audit.read");
    expect(ROLE_PERMISSIONS.VIEWER).not.toContain("audit.read");
  });

  it("keeps reviewer capabilities off analysts and viewers beyond review", () => {
    expect(ROLE_PERMISSIONS.ANALYST).toContain("findings.review");
    expect(ROLE_PERMISSIONS.ANALYST).not.toContain("findings.confirm");
    expect(ROLE_PERMISSIONS.VIEWER).not.toContain("findings.review");
  });

  it("hasPermission reflects the authenticated user's grant set", () => {
    resetPermissions("adminSet");
    expect(hasPermission("users.manage")).toBe(true);
    resetPermissions("viewerSet");
    expect(hasPermission("users.manage")).toBe(false);
    expect(hasPermission("case.read")).toBe(true);
    useAuthStore.setState({ status: "anonymous", permissions: [], roles: [], user: null, error: null });
  });
});