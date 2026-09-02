import { describe, expect, it } from "vitest";
import { mockApi } from "@/api/mock";
import { realApi } from "@/api/real";

const SERVICE_KEYS = [
  "auth",
  "cases",
  "entities",
  "evidence",
  "graph",
  "analytics",
  "findings",
  "audit",
  "timeline",
  "users",
  "admin",
] as const;

type Services = { [K in (typeof SERVICE_KEYS)[number]]: object };

describe("mock/real adapter surface parity", () => {
  it("every service exposes the same methods on mock and real", () => {
    const mock = mockApi as unknown as Services;
    const real = realApi as unknown as Services;
    const mismatches: string[] = [];
    for (const svc of SERVICE_KEYS) {
      const k = svc as keyof Services;
      const m = Object.keys(mock[k] ?? {}).sort();
      const r = Object.keys(real[k] ?? {}).sort();
      if (JSON.stringify(m) !== JSON.stringify(r)) {
        mismatches.push(`${svc}: mock=[${m}] real=[${r}]`);
      }
    }
    expect(mismatches).toEqual([]);
  });
});