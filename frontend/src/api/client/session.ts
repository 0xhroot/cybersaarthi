/**
 * Client-side auth session holder.
 *
 * The real adapter reads the bearer token from here; the auth store writes it on
 * login/me. Kept dependency-free so both adapters and the store can share it
 * without circular imports.
 */

const TOKEN_KEY = "cybersaarthi.token";
const USER_KEY = "cybersaarthi.user";

export interface StoredUser {
  id: string;
  username: string;
  email: string;
  is_active: boolean;
}

let accessToken: string | null = null;
let currentUser: StoredUser | null = null;
let currentPermissions: string[] = [];
let onUnauthorized: (() => void) | null = null;

export const authSession = {
  getToken(): string | null {
    return accessToken;
  },
  getUser(): StoredUser | null {
    return currentUser;
  },
  get permissions(): string[] {
    return currentPermissions;
  },
  setPermissions(permissions: string[]): void {
    currentPermissions = permissions;
  },
  setSession(token: string, user: StoredUser): void {
    accessToken = token;
    currentUser = user;
    try {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    } catch {
      /* storage unavailable (private mode) — keep in memory only */
    }
  },
  setUser(user: StoredUser): void {
    currentUser = user;
    try {
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    } catch {
      /* ignore */
    }
  },
  clear(): void {
    accessToken = null;
    currentUser = null;
    currentPermissions = [];
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    } catch {
      /* ignore */
    }
  },
  setOnUnauthorized(handler: (() => void) | null): void {
    onUnauthorized = handler;
  },
  fireUnauthorized(): void {
    onUnauthorized?.();
  },
  restore(): { token: string | null; user: StoredUser | null } {
    if (accessToken) return { token: accessToken, user: currentUser };
    try {
      const token = localStorage.getItem(TOKEN_KEY);
      const rawUser = localStorage.getItem(USER_KEY);
      if (token) accessToken = token;
      if (rawUser) {
        try {
          currentUser = JSON.parse(rawUser) as StoredUser;
        } catch {
          currentUser = null;
        }
      }
      return { token: accessToken, user: currentUser };
    } catch {
      return { token: accessToken, user: currentUser };
    }
  },
};