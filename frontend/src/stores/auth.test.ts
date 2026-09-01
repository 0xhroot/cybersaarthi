import { beforeEach, describe, expect, it } from "vitest";
import { useAuthStore } from "@/stores/auth";
import { authSession } from "@/api/client/session";

beforeEach(() => {
  useAuthStore.setState({ status: "idle", user: null, roles: [], permissions: [], error: null });
  authSession.clear();
});

describe("auth store", () => {
  it("boots as anonymous when no session exists", async () => {
    await useAuthStore.getState().bootstrap();
    expect(useAuthStore.getState().status).toBe("anonymous");
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("logs in with demo credentials and restores roles/permissions", async () => {
    await useAuthStore.getState().login("admin", "admin-dev-password");
    const state = useAuthStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.user?.username).toBe("admin");
    expect(state.roles).toEqual(["ADMIN"]);
    expect(state.permissions).toContain("audit.read");
    expect(state.permissions).toContain("users.manage");
  });

  it("rejects bad credentials and exposes an error", async () => {
    await expect(useAuthStore.getState().login("admin", "wrong")).rejects.toBeTruthy();
    expect(useAuthStore.getState().status).toBe("anonymous");
    expect(useAuthStore.getState().error).toBeTruthy();
  });

  it("logout clears the authenticated session", async () => {
    await useAuthStore.getState().login("viewer", "viewer-demo-password");
    expect(useAuthStore.getState().status).toBe("authenticated");
    useAuthStore.getState().logout();
    const state = useAuthStore.getState();
    expect(state.status).toBe("anonymous");
    expect(state.user).toBeNull();
    expect(state.permissions).toEqual([]);
  });

  it("registers a PENDING account without establishing a session", async () => {
    await useAuthStore.getState().register({
      username: "requestor",
      email: "requestor@cybersaarthi.test",
      password: "some-password!",
    });
    const state = useAuthStore.getState();
    expect(state.error).toBeNull();
    // Registration must not imply a session (account is PENDING until approval).
    expect(state.user).toBeNull();
    expect(state.roles).toEqual([]);
  });

  it("surfaces duplicate username as a register error", async () => {
    await useAuthStore.getState().register({
      username: "taken",
      email: "taken@cybersaarthi.test",
      password: "some-password!",
    });
    await expect(
      useAuthStore.getState().register({
        username: "taken",
        email: "other@cybersaarthi.test",
        password: "some-password!",
      }),
    ).rejects.toBeTruthy();
    expect(useAuthStore.getState().error).toBeTruthy();
  });
});