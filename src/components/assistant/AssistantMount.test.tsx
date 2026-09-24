/**
 * AssistantMount — the legacy n8n widget renders only when the flag is off. With the flag on
 * it never renders (it would send chat text to a service the Privacy Policy does not name): the
 * new widget mounts when enabled, for consent, or to say why it can't answer (sign in, today's
 * limit); otherwise nothing shows.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

const authState = { isAuthenticated: true, user: { id: "u1" }, isLoading: false };
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => authState }));
vi.mock("@/components/chat/ChatWidget", () => ({ default: () => <div data-testid="legacy-widget" /> }));
vi.mock("@/components/assistant/AssistantWidget", () => ({ default: () => <div data-testid="v2-widget" /> }));

const flag = { on: true, down: false };
const statusMock = vi.fn();
vi.mock("@/lib/assistantApi", () => ({
  get ASSISTANT_V2_FLAG() {
    return flag.on;
  },
  // a plain async function: a spy returning a rejected promise trips vitest's result
  // tracking as an unhandled rejection even though the component catches it
  assistantApi: {
    status: async () => {
      if (flag.down) throw new Error("down");
      return statusMock();
    },
  },
}));

async function mount() {
  const { default: AssistantMount } = await import("./AssistantMount");
  return render(
    <MemoryRouter>
      <AssistantMount />
    </MemoryRouter>,
  );
}

describe("AssistantMount", () => {
  beforeEach(() => {
    statusMock.mockReset();
    flag.down = false;
  });

  it("keeps the legacy widget when the build flag is off (no status call)", async () => {
    flag.on = false;
    await mount();
    expect(screen.getByTestId("legacy-widget")).toBeInTheDocument();
    expect(statusMock).not.toHaveBeenCalled();
  });

  it("mounts v2 when the backend enables it", async () => {
    flag.on = true;
    statusMock.mockResolvedValue({ enabled: true, consent_required: false });
    await mount();
    await waitFor(() => expect(screen.getByTestId("v2-widget")).toBeInTheDocument());
    expect(screen.queryByTestId("legacy-widget")).toBeNull();
  });

  it("mounts v2 for a signed-in user who still has to consent", async () => {
    flag.on = true;
    statusMock.mockResolvedValue({ enabled: false, reason: "CONSENT_REQUIRED", consent_required: true });
    await mount();
    await waitFor(() => expect(screen.getByTestId("v2-widget")).toBeInTheDocument());
  });

  it("shows nothing (never the legacy widget) when v2 is switched off for this caller", async () => {
    flag.on = true;
    statusMock.mockResolvedValue({ enabled: false, reason: "ASSISTANT_DISABLED", consent_required: false });
    await mount();
    await waitFor(() => expect(statusMock).toHaveBeenCalled());
    expect(screen.queryByTestId("legacy-widget")).toBeNull();
    expect(screen.queryByTestId("v2-widget")).toBeNull();
  });

  it("shows nothing (never the legacy widget) when the backend is unreachable", async () => {
    flag.on = true;
    flag.down = true;
    await mount();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("legacy-widget")).toBeNull();
    expect(screen.queryByTestId("v2-widget")).toBeNull();
  });

  it("opens v2 to say why when the caller can act on it (sign in, today's limit)", async () => {
    flag.on = true;
    for (const reason of ["SIGN_IN_REQUIRED", "DAILY_CAP"]) {
      statusMock.mockResolvedValue({ enabled: false, reason, consent_required: false });
      const view = await mount();
      await waitFor(() => expect(screen.getByTestId("v2-widget")).toBeInTheDocument());
      expect(screen.queryByTestId("legacy-widget")).toBeNull();
      view.unmount();
    }
  });
});
