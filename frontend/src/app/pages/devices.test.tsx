import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { FieldDevice } from "@/types/domain";

const fieldDevicesHook = vi.hoisted(() => vi.fn());
const approveHook = vi.hoisted(() => vi.fn());
const revokeHook = vi.hoisted(() => vi.fn());
const healthHook = vi.hoisted(() => vi.fn());

vi.mock("@/hooks/queries", () => ({
  useFieldDevices: (cid: string) => fieldDevicesHook(cid),
  useApproveFieldDevice: (cid: string) => approveHook(cid),
  useRevokeFieldDevice: (cid: string) => revokeHook(cid),
  useServerHealth: () => healthHook(),
}));

vi.mock("@/lib/permissions", () => ({
  useCan: () => true,
}));

import FieldDevicesPage from "@/app/pages/devices";

const PENDING: FieldDevice = {
  id: "dev-1",
  case_id: "case-1",
  platform: "android_mobile",
  serial: "AGENT-ALPHA",
  model: "Pixel 9",
  firmware_version: null,
  signature_algorithm: "RSA-SHA256",
  status: "pending",
  approved_by: null,
  last_seen_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

const APPROVED: FieldDevice = {
  id: "dev-2",
  case_id: "case-1",
  platform: "android_mobile",
  serial: "AGENT-BRAVO",
  model: null,
  firmware_version: null,
  signature_algorithm: "Ed25519",
  status: "approved",
  approved_by: "u-admin",
  last_seen_at: new Date().toISOString(),
  created_at: "2026-01-02T00:00:00Z",
};

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={["/app/cases/case-1"]}>
      <FieldDevicesPage />
    </MemoryRouter>,
  );

describe("field devices page", () => {
  it("lists enrolled devices with liveness and enrolment times", () => {
    fieldDevicesHook.mockReturnValue({
      data: { items: [PENDING, APPROVED], total: 2, limit: 100, offset: 0 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    healthHook.mockReturnValue({ data: { status: "ok", service: "cybersaarthi", version: "0.1.0" } });

    renderPage();

    expect(screen.getByText("AGENT-ALPHA")).toBeInTheDocument();
    expect(screen.getByText("AGENT-BRAVO")).toBeInTheDocument();
    expect(screen.getByText("pending")).toBeInTheDocument();
    expect(screen.getByText("approved")).toBeInTheDocument();
    expect(screen.getByText("2 enrolled")).toBeInTheDocument();
  });

  it("exposes approve (pending) and revoke (approved) actions", () => {
    fieldDevicesHook.mockReturnValue({
      data: { items: [PENDING, APPROVED], total: 2, limit: 100, offset: 0 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    approveHook.mockReturnValue({ mutateAsync: vi.fn(() => Promise.resolve(APPROVED)), isPending: false });
    revokeHook.mockReturnValue({ mutateAsync: vi.fn(() => Promise.resolve(PENDING)), isPending: false });

    renderPage();

    expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /revoke/i })).toBeInTheDocument();
  });

  it("renders a pairing QR dialog with the live server fingerprint", async () => {
    fieldDevicesHook.mockReturnValue({
      data: { items: [], total: 0, limit: 100, offset: 0 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    healthHook.mockReturnValue({ data: { status: "ok", service: "cybersaarthi", version: "0.1.0" } });

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /pair new device/i }));

    expect(await screen.findByText(/pair an android field device/i)).toBeInTheDocument();

    await waitFor(() => {
      const qr = document.querySelector('img[alt="Pairing QR code"]');
      expect(qr).not.toBeNull();
      expect(qr?.getAttribute("src")).toContain("data:image/svg+xml");
    });

    expect(screen.getByText(/34edcf12e59a5c1b846bca384e9a89c6ecb39139c61daf14bdace2f04ef28e78/)).toBeInTheDocument();
  });

  it("blocks pairing when the backend health is unavailable", async () => {
    fieldDevicesHook.mockReturnValue({
      data: { items: [], total: 0, limit: 100, offset: 0 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    healthHook.mockReturnValue({ data: undefined, isError: true });

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /pair new device/i }));

    expect(await screen.findByText(/pair an android field device/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/could not read the server health/i)).toBeInTheDocument();
    });
    expect(document.querySelector('img[alt="Pairing QR code"]')).toBeNull();
  });
});