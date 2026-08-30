import { create } from "zustand";
import { api } from "@/api";
import { authSession } from "@/api/client/session";
import type { Role, UserOut } from "@/types/domain";

export type AuthStatus = "idle" | "loading" | "authenticated" | "anonymous";

interface AuthState {
  status: AuthStatus;
  user: UserOut | null;
  roles: Role[];
  permissions: string[];
  error: string | null;
  bootstrap: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  restore: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  status: "idle",
  user: null,
  roles: [],
  permissions: [],
  error: null,

  restore() {
    const restored = authSession.restore();
    if (!restored) {
      set({ status: "anonymous", user: null, roles: [], permissions: [] });
      return;
    }
    set({ status: "loading", user: get().user, roles: get().roles, permissions: get().permissions });
  },

  async bootstrap() {
    const restored = authSession.restore();
    if (!restored) {
      set({ status: "anonymous", user: null, roles: [], permissions: [] });
      return;
    }
    set({ status: "loading", error: null });
    try {
      const me = await api.auth.me();
      authSession.setPermissions(me.permissions);
      set({
        status: "authenticated",
        user: me.user,
        roles: me.roles,
        permissions: me.permissions,
      });
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 401) {
        authSession.clear();
        set({ status: "anonymous", user: null, roles: [], permissions: [] });
      } else {
        set({ status: "anonymous", user: null, roles: [], permissions: [], error: (err as Error).message });
      }
    }
  },

  async login(username, password) {
    set({ status: "loading", error: null });
    try {
      const token = await api.auth.login({ username, password });
      authSession.setSession(token.access_token, token.user);
      const me = await api.auth.me();
      authSession.setPermissions(me.permissions);
      set({
        status: "authenticated",
        user: me.user,
        roles: me.roles,
        permissions: me.permissions,
        error: null,
      });
    } catch (err) {
      set({ status: "anonymous", error: (err as Error).message });
      throw err;
    }
  },

  logout() {
    authSession.clear();
    set({ status: "anonymous", user: null, roles: [], permissions: [], error: null });
  },
}));

export function useIsAuthenticated(): boolean {
  return useAuthStore((s) => s.status === "authenticated");
}