import { useAuthStore } from "@/stores/auth";

export type Permission =
  | "case.read"
  | "case.create"
  | "case.update"
  | "case.archive"
  | "evidence.read"
  | "evidence.upload"
  | "ingestion.run"
  | "analytics.run"
  | "findings.read"
  | "findings.review"
  | "findings.confirm"
  | "findings.dismiss"
  | "users.manage"
  | "audit.read";

export const ALL_PERMISSIONS: Permission[] = [
  "case.read",
  "case.create",
  "case.update",
  "case.archive",
  "evidence.read",
  "evidence.upload",
  "ingestion.run",
  "analytics.run",
  "findings.read",
  "findings.review",
  "findings.confirm",
  "findings.dismiss",
  "users.manage",
  "audit.read",
];

export const ROLE_PERMISSIONS: Record<string, Permission[]> = {
  ADMIN: ALL_PERMISSIONS,
  INVESTIGATOR: ALL_PERMISSIONS.filter((p) => p !== "users.manage"),
  ANALYST: [
    "case.read",
    "evidence.read",
    "analytics.run",
    "findings.read",
    "findings.review",
  ],
  VIEWER: ["case.read", "evidence.read", "findings.read"],
};

/** Non-reactive permission check for event handlers, guards and adapters. */
export function hasPermission(permission: Permission): boolean {
  return useAuthStore.getState().permissions.includes(permission);
}

export function hasAnyPermission(permissions: Permission[]): boolean {
  const owned = useAuthStore.getState().permissions;
  return permissions.some((p) => owned.includes(p));
}

/** Reactive hook — re-renders the component when permission sets change. */
export function useCan(permission: Permission | Permission[]): boolean {
  const owned = useAuthStore((s) => s.permissions);
  if (Array.isArray(permission)) {
    return permission.some((p) => owned.includes(p));
  }
  return owned.includes(permission);
}

export function useCanAny(permissions: Permission[]): boolean {
  const owned = useAuthStore((s) => s.permissions);
  return permissions.some((p) => owned.includes(p));
}