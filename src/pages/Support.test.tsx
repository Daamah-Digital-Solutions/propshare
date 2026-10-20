import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Support from "./Support";
import { OPEN_ASSISTANT_EVENT } from "@/lib/assistantEvents";

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ isAuthenticated: false }) }));

const renderPage = () =>
  render(
    <MemoryRouter>
      <Support />
    </MemoryRouter>,
  );

describe("Support page", () => {
  afterEach(() => vi.restoreAllMocks());

  it("leads with PropShare AI instead of the unstaffed message form", () => {
    renderPage();
    expect(screen.queryByText("Message Us")).not.toBeInTheDocument();
    expect(screen.queryByText(/we reply by email or WhatsApp/)).not.toBeInTheDocument();
    // the box at the top and the first channel card
    expect(screen.getAllByRole("heading", { name: "Ask PropShare AI" })).toHaveLength(2);
    expect(screen.getByTestId("propshare-ai")).toHaveTextContent(/full customer service/);
    expect(screen.getByTestId("propshare-ai")).toHaveTextContent(/documents, certificates and statements/);
  });

  it("opens the assistant from the button", () => {
    const opened = vi.fn((e: Event) => e.preventDefault());
    window.addEventListener(OPEN_ASSISTANT_EVENT, opened);
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Chat with PropShare AI/ }));
    expect(opened).toHaveBeenCalledTimes(1);
    window.removeEventListener(OPEN_ASSISTANT_EVENT, opened);
  });

  it("points to the ticket form when no assistant is on the page", () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Chat with PropShare AI/ }));
    expect(scroll).toHaveBeenCalled();
  });
});
