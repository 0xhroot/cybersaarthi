import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Badge, Dot } from "@/components/ui/badge";
import { ApiError } from "@/types/api";

describe("error and empty state surfaces", () => {
  it("renders an empty state with title, description and action", () => {
    render(<EmptyState title="No cases" description="Create one to begin." action={{ label: "Create", onClick: () => {} }} />);
    expect(screen.getByText("No cases")).toBeInTheDocument();
    expect(screen.getByText("Create one to begin.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
  });

  it("maps a 403 API error to the scoped not-authorized message", () => {
    render(<ErrorState error={new ApiError({ status: 403, code: "FORBIDDEN", message: "forbidden" })} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/No access/i);
    expect(screen.getByRole("alert")).toHaveTextContent(/permit/i);
  });

  it("maps a 401 API error to the session-expired message", () => {
    render(<ErrorState error={new ApiError({ status: 401, code: "UNAUTHORIZED", message: "no token" })} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/session has expired/i);
  });

  it("renders badges and dots with their label text", () => {
    render(
      <>
        <Badge tone="success">Ingested</Badge>
        <Dot className="bg-success" />
      </>,
    );
    expect(screen.getByText("Ingested")).toBeInTheDocument();
  });
});