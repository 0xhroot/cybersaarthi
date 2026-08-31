import { describe, expect, it } from "vitest";
import type { CaseCreateRequest, CaseUpdateRequest, WritableCaseStatus } from "@/types/domain";

/**
 * F07 regression: the backend Pydantic schema rejects `archived` on
 * create/update with 422, so the request types must never allow sending it
 * even though reads must tolerate it. These are compile-time assertions.
 */
describe("F07 case status request types", () => {
  it("excludes the read-only archived status from writable statuses", () => {
    const writable: WritableCaseStatus = "open";
    expect(writable).toBe("open");
    // "closed" and "in_progress" are valid too.
    const writable2: WritableCaseStatus[] = ["open", "in_progress", "closed"];
    expect(writable2).toHaveLength(3);
  });

  it("allows open/in_progress/closed in the create request", () => {
    const create: CaseCreateRequest = { title: "x", status: "in_progress" };
    expect(create.status).toBe("in_progress");
    const update: CaseUpdateRequest = { status: "closed" };
    expect(update.status).toBe("closed");
  });

  it("tolerates archived when reading a case (read type is unaffected)", () => {
    const readStatus: import("@/types/domain").CaseStatus = "archived";
    expect(readStatus).toBe("archived");
  });

  // Compile-time guards: submitting `archived` must fail typechecking.
  it("rejects archived at compile time on create and update requests", () => {
    // @ts-expect-error - archived is read-only and must not be sendable on create
    const invalidCreateStatus: CaseCreateRequest = { title: "x", status: "archived" };
    // @ts-expect-error - archived is read-only and must not be sendable on update
    const invalidUpdateStatus: CaseUpdateRequest = { status: "archived" };
    void invalidCreateStatus;
    void invalidUpdateStatus;
  });
});
