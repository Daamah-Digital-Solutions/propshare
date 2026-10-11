/**
 * The public claim page (client, 2026-10-07): a form anyone can open, where the person an
 * account holder named reports the holder's death and claims with the beneficiary certificate
 * and their own identity document. It says plainly that the transfer goes to the claimant's
 * OWN verified account, and a signed-in claimant follows their claims on the same page.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ submit: vi.fn(), mine: vi.fn(), addDocument: vi.fn(), resend: vi.fn() }));
const { toast, auth, ApiError } = vi.hoisted(() => {
  class ApiError extends Error {
    status: number;
    constructor(_code: string, message: string, status: number) {
      super(message);
      this.status = status;
    }
  }
  const auth: { current: { user: Record<string, unknown> | null; isAuthenticated: boolean } } = {
    current: { user: null, isAuthenticated: false },
  };
  return { toast: vi.fn(), auth, ApiError };
});
vi.mock("@/lib/api", () => ({
  ApiError,
  estateClaimsApi: api,
  authApi: { resendVerification: api.resend },
}));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast }) }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth.current }));

import EstateClaim from "./EstateClaim";

const CLAIM = {
  id: "c1",
  reference: "CLM-5D2E-88A1",
  status: "submitted",
  status_label: "Received",
  reason: "death",
  holder_name: "Ahmed Mansouri",
  certificate_no: "CPB-3FA4-91C2",
  message: null,
  documents: [
    { kind: "certificate", filename: "certificate.pdf" },
    { kind: "identity", filename: "passport.jpg" },
  ],
  can_add_documents: true,
  created_at: "2026-10-08T10:00:00Z",
  updated_at: "2026-10-08T10:00:00Z",
};

const file = (name: string, type: string, size = 2000) => {
  const f = new File(["x"], name, { type });
  Object.defineProperty(f, "size", { value: size });
  return f;
};

function mount(path = "/estate-claim") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <EstateClaim />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const fill = (label: RegExp | string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe("EstateClaim", () => {
  beforeEach(() => {
    Object.values(api).forEach((m) => m.mockReset());
    toast.mockReset();
    auth.current = { user: null, isAuthenticated: false };
    api.mine.mockResolvedValue([]);
    window.scrollTo = vi.fn();
  });

  it("explains the procedure to a visitor, and that the transfer goes to their own account", () => {
    mount("/estate-claim?certificate=CPB-3FA4-91C2");
    expect(screen.getByRole("heading", { name: "Report a Death or Make a Claim" })).toBeInTheDocument();
    for (const step of ["Send the claim", "We verify it", "Your own account", "The transfer"]) {
      expect(screen.getByRole("heading", { name: step })).toBeInTheDocument();
    }
    const notice = screen.getByTestId("own-account-notice");
    expect(notice).toHaveTextContent("You need an account of your own");
    expect(notice).toHaveTextContent(/Nobody is given the account holder's account, password or records/);
    expect(within(notice).getByRole("link", { name: "Create your account" })).toHaveAttribute(
      "href",
      "/auth?tab=register",
    );
    // the certificate's QR code opens the page with its number filled in
    expect(screen.getByLabelText(/Certificate number/)).toHaveValue("CPB-3FA4-91C2");
    // a death is the reason by default, with its date
    expect(screen.getByLabelText(/Date of death/)).toBeInTheDocument();
    // a visitor has no claims list, and is not asked for one
    expect(screen.queryByTestId("my-claims")).toBeNull();
    expect(api.mine).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: /No certificate\? Contact support/ })).toHaveAttribute("href", "/support");
  });

  it("does not send an incomplete form, and says what is missing", () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: /Send the claim/ }));
    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ title: "The form is not complete", description: "Enter your full name." }),
    );
    fill(/Your full name/, "Fatima Mansouri");
    fill(/Email address/, "fatima@heirs.io");
    fill(/^Country/, "United Arab Emirates");
    fill(/Account holder's full name/, "Ahmed Mansouri");
    fill(/Date of death/, "2026-09-01");
    fill(/Certificate number/, "CPB-3FA4-91C2");
    fireEvent.click(screen.getByRole("button", { name: /Send the claim/ }));
    expect(toast).toHaveBeenLastCalledWith(
      expect.objectContaining({ description: "Attach the beneficiary certificate." }),
    );
    expect(api.submit).not.toHaveBeenCalled();
  });

  it("sends the claim with its documents and shows the reference", async () => {
    api.submit.mockResolvedValue(CLAIM);
    mount("/estate-claim?certificate=CPB-3FA4-91C2");
    fill(/Your full name/, "Fatima Mansouri");
    fill(/Email address/, " fatima@heirs.io ");
    fill(/^Phone/, "+971500000001");
    fill(/^Country/, "United Arab Emirates");
    fill(/Your relationship/, "Daughter");
    fill(/Document number/, "A1234567");
    fill(/Account holder's full name/, "Ahmed Mansouri");
    fill(/Date of death/, "2026-09-01");
    fill(/Anything our team should know/, "He passed away in September.");

    const certificate = file("certificate.pdf", "application/pdf");
    const front = file("passport.jpg", "image/jpeg");
    const death = file("death-certificate.pdf", "application/pdf");
    fireEvent.change(screen.getByTestId("claim-certificate"), { target: { files: [certificate] } });
    fireEvent.change(screen.getByTestId("claim-identity"), { target: { files: [front] } });
    fireEvent.change(screen.getByTestId("claim-evidence"), { target: { files: [death] } });
    // a file that is not a photo or a PDF is refused on the spot
    fireEvent.change(screen.getByTestId("claim-identity"), { target: { files: [file("id.heic", "image/heic")] } });
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: "File not added" }));

    fireEvent.click(screen.getByRole("button", { name: /Send the claim/ }));
    expect(toast).toHaveBeenLastCalledWith(
      expect.objectContaining({ description: "Confirm the declaration at the end of the form." }),
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "Declaration" }));
    fireEvent.click(screen.getByRole("button", { name: /Send the claim/ }));

    await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(1));
    expect(api.submit).toHaveBeenCalledWith(
      {
        claimant_name: "Fatima Mansouri",
        claimant_email: "fatima@heirs.io",
        claimant_phone: "+971500000001",
        claimant_country: "United Arab Emirates",
        claimant_id_type: "Passport",
        claimant_id_number: "A1234567",
        relationship: "Daughter",
        holder_name: "Ahmed Mansouri",
        holder_email: undefined,
        certificate_no: "CPB-3FA4-91C2",
        reason: "death",
        date_of_death: "2026-09-01",
        details: "He passed away in September.",
      },
      { certificate, identity: [front], evidence: [death] },
    );

    const done = await screen.findByTestId("claim-sent");
    expect(within(done).getByTestId("claim-reference")).toHaveTextContent("CLM-5D2E-88A1");
    expect(done).toHaveTextContent("We sent it to fatima@heirs.io as well.");
    // what a visitor does next: their own account
    expect(within(done).getByRole("link", { name: "Create your account" })).toHaveAttribute(
      "href",
      "/auth?tab=register",
    );
    // the form is gone: the same claim is not sent twice
    expect(screen.queryByRole("button", { name: /Send the claim/ })).toBeNull();
  });

  it("does not start an upload the server would refuse: the files together are too large", () => {
    mount("/estate-claim?certificate=CPB-3FA4-91C2");
    fill(/Your full name/, "Fatima Mansouri");
    fill(/Email address/, "fatima@heirs.io");
    fill(/^Country/, "UAE");
    fill(/Account holder's full name/, "Ahmed Mansouri");
    fill(/Date of death/, "2026-09-01");
    const MB = 1024 * 1024;
    // each photo is under the 10 MB a single file may be; together they pass 25 MB
    fireEvent.change(screen.getByTestId("claim-certificate"), { target: { files: [file("c.pdf", "application/pdf")] } });
    fireEvent.change(screen.getByTestId("claim-identity"), {
      target: { files: [file("front.jpg", "image/jpeg", 9 * MB), file("back.jpg", "image/jpeg", 9 * MB)] },
    });
    fireEvent.change(screen.getByTestId("claim-evidence"), {
      target: { files: [file("death-certificate.jpg", "image/jpeg", 9 * MB)] },
    });
    expect(toast).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("checkbox", { name: "Declaration" }));
    fireEvent.click(screen.getByRole("button", { name: /Send the claim/ }));
    expect(toast).toHaveBeenLastCalledWith(
      expect.objectContaining({
        title: "The form is not complete",
        description: expect.stringMatching(/^The files together are larger than 25 MB\./),
      }),
    );
    expect(api.submit).not.toHaveBeenCalled();
  });

  it("says so when the web server refuses the upload as too large", async () => {
    api.submit.mockRejectedValue(new ApiError("HTTP_ERROR", "Request failed (413)", 413));
    mount("/estate-claim?certificate=CPB-3FA4-91C2");
    fill(/Your full name/, "Fatima Mansouri");
    fill(/Email address/, "fatima@heirs.io");
    fill(/^Country/, "UAE");
    fill(/Account holder's full name/, "Ahmed Mansouri");
    fill(/Date of death/, "2026-09-01");
    fireEvent.change(screen.getByTestId("claim-certificate"), { target: { files: [file("c.pdf", "application/pdf")] } });
    fireEvent.change(screen.getByTestId("claim-identity"), { target: { files: [file("id.png", "image/png")] } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Declaration" }));
    fireEvent.click(screen.getByRole("button", { name: /Send the claim/ }));
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "The claim was not sent",
          description: expect.stringMatching(/^The files together are larger than 25 MB\./),
        }),
      ),
    );
    expect(screen.queryByTestId("claim-sent")).toBeNull();
  });

  it("says why the server refused a claim, and keeps the form", async () => {
    api.submit.mockRejectedValue(new ApiError("CLAIM_OPEN", "You already have a claim with this certificate in review.", 409));
    mount("/estate-claim?certificate=CPB-3FA4-91C2");
    fill(/Your full name/, "Fatima Mansouri");
    fill(/Email address/, "fatima@heirs.io");
    fill(/^Country/, "UAE");
    fill(/Account holder's full name/, "Ahmed Mansouri");
    fill(/Date of death/, "2026-09-01");
    fireEvent.change(screen.getByTestId("claim-certificate"), { target: { files: [file("c.pdf", "application/pdf")] } });
    fireEvent.change(screen.getByTestId("claim-identity"), { target: { files: [file("id.png", "image/png")] } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Declaration" }));
    fireEvent.click(screen.getByRole("button", { name: /Send the claim/ }));
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "The claim was not sent",
          description: "You already have a claim with this certificate in review.",
        }),
      ),
    );
    expect(screen.getByLabelText(/Your full name/)).toHaveValue("Fatima Mansouri");
    expect(screen.queryByTestId("claim-sent")).toBeNull();
  });

  it("a signed-in claimant has their details filled in, follows their claims and adds a document", async () => {
    auth.current = {
      isAuthenticated: true,
      user: {
        id: "u1",
        email: "fatima@heirs.io",
        email_verified: true,
        full_name: "Fatima Mansouri",
        kyc_status: "pending",
      },
    };
    api.mine.mockResolvedValue([
      { ...CLAIM, status: "needs_info", status_label: "Waiting for the claimant", message: "The official death certificate." },
      { ...CLAIM, id: "c0", reference: "CLM-0000-0001", status: "rejected", status_label: "Rejected", message: "Not matching.", can_add_documents: false },
    ]);
    api.addDocument.mockResolvedValue({ ...CLAIM, status: "in_review", status_label: "In review" });
    mount();

    await waitFor(() => expect(screen.getByLabelText(/Your full name/)).toHaveValue("Fatima Mansouri"));
    expect(screen.getByLabelText(/Email address/)).toHaveValue("fatima@heirs.io");
    // not verified yet: that is the step left for them
    expect(within(screen.getByTestId("own-account-notice")).getByRole("link", { name: "Verify your identity" })).toHaveAttribute("href", "/kyc");
    // their address is confirmed: nothing to ask about it
    expect(screen.queryByTestId("confirm-email-notice")).toBeNull();

    const claims = await screen.findByTestId("my-claims");
    expect(within(claims).getByText("CLM-5D2E-88A1")).toBeInTheDocument();
    expect(within(claims).getByText("Waiting for the claimant")).toBeInTheDocument();
    expect(within(claims).getByText("The official death certificate.")).toBeInTheDocument();
    expect(within(claims).getByText("Rejected")).toBeInTheDocument();
    // only an open claim takes another document
    expect(within(claims).getAllByRole("button", { name: /Add a document/ })).toHaveLength(1);

    const death = file("death-certificate.pdf", "application/pdf");
    fireEvent.change(screen.getByTestId("claim-file-c1"), { target: { files: [death] } });
    await waitFor(() => expect(api.addDocument).toHaveBeenCalledWith("c1", "evidence", death));
    await waitFor(() => expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: "Document added" })));
  });

  it("a member whose address is not confirmed is told why an earlier claim is not here, and gets a new link", async () => {
    auth.current = {
      isAuthenticated: true,
      user: {
        id: "u1",
        email: "fatima@heirs.io",
        email_verified: false,
        full_name: "Fatima Mansouri",
        kyc_status: "verified",
      },
    };
    api.resend.mockResolvedValue(undefined);
    mount();

    const notice = screen.getByTestId("confirm-email-notice");
    expect(notice).toHaveTextContent("Confirm your email address");
    expect(notice).toHaveTextContent(/A claim sent with fatima@heirs.io before you signed in shows here/);
    fireEvent.click(within(notice).getByRole("button", { name: "Send me the confirmation link" }));
    await waitFor(() => expect(api.resend).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Confirmation link sent",
          description: "Open the email we sent to fatima@heirs.io and follow the link.",
        }),
      ),
    );
    // one link per visit: the button does not send a second one
    expect(within(notice).getByRole("button", { name: "Link sent" })).toBeDisabled();
  });

  it("says why a new confirmation link could not be sent", async () => {
    auth.current = {
      isAuthenticated: true,
      user: { id: "u1", email: "fatima@heirs.io", email_verified: false, full_name: "Fatima Mansouri", kyc_status: "verified" },
    };
    api.resend.mockRejectedValue(
      new ApiError("TOO_MANY_REQUESTS", "A verification email was sent recently. Please check your inbox.", 429),
    );
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Send me the confirmation link" }));
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Could not send the link",
          description: "A verification email was sent recently. Please check your inbox.",
        }),
      ),
    );
    // they can try again later
    expect(screen.getByRole("button", { name: "Send me the confirmation link" })).toBeEnabled();
  });
});
