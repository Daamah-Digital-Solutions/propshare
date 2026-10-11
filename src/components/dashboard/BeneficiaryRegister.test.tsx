/**
 * The beneficiary register (client, 2026-10-07): a person on it carries a copy of their
 * identity document, can be edited at any time (there was only Delete), and has a certificate
 * to download. And once a transfer event is recorded for the account, the register is closed.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  list: vi.fn(),
  add: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  addDocument: vi.fn(),
  removeDocument: vi.fn(),
  fetchDocument: vi.fn(),
  certificate: vi.fn(),
}));
const { toast, saveBlob, ApiError } = vi.hoisted(() => {
  class ApiError extends Error {
    status: number;
    code: string;
    constructor(code: string, message: string, status: number) {
      super(message);
      this.code = code;
      this.status = status;
    }
  }
  return { toast: vi.fn(), saveBlob: vi.fn(), ApiError };
});
vi.mock("@/lib/api", () => ({ ApiError, estateApi: api }));
vi.mock("@/lib/certificates", () => ({ saveBlob }));
vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast }) }));

import { BeneficiaryRegister } from "./BeneficiaryRegister";

const FATIMA = {
  id: "b1",
  full_name: "Fatima Mansouri",
  relationship: "Daughter",
  email: "fatima@heirs.io",
  phone: "+971500000001",
  allocation_pct: 60,
  notes: "My eldest",
  status: "pending",
  is_user: false,
  meta: { role: "heir", idType: "Passport", idNumber: "A1234567", scope: ["ownership", "wallet"], trigger: "death" },
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-03T00:00:00Z",
  certificate_no: "CPB-3FA4-91C2",
  version: 2,
  documents: [
    { id: "d1", filename: "passport.jpg", content_type: "image/jpeg", size: 1200, uploaded_at: "2026-10-01T00:00:00Z" },
  ],
  locked: false,
};
const OMAR = {
  ...FATIMA,
  id: "b2",
  full_name: "Omar Mansouri",
  relationship: "Son",
  email: null,
  allocation_pct: 20,
  notes: null,
  certificate_no: "CPB-0000-AAAA",
  version: 1,
  documents: [],
};

const file = (name: string, type: string, size = 2000) => {
  const f = new File(["x"], name, { type });
  Object.defineProperty(f, "size", { value: size });
  return f;
};

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <BeneficiaryRegister />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BeneficiaryRegister", () => {
  beforeEach(() => {
    Object.values(api).forEach((m) => m.mockReset());
    toast.mockReset();
    saveBlob.mockReset();
    api.list.mockResolvedValue([FATIMA, OMAR]);
  });

  it("shows each person's certificate number, its version and whether an ID copy is on file", async () => {
    mount();
    const card = await screen.findByTestId("beneficiary-b1");
    expect(within(card).getByText("Fatima Mansouri")).toBeInTheDocument();
    expect(within(card).getByText("CPB-3FA4-91C2 · v2")).toBeInTheDocument();
    expect(within(card).getByText("ID copy on file (1)")).toBeInTheDocument();
    expect(within(screen.getByTestId("beneficiary-b2")).getByText("No ID copy on file")).toBeInTheDocument();
    // what the status means, said as it is (it claimed "Legally acknowledged")
    expect(within(card).getByText("No verified account yet")).toBeInTheDocument();
    expect(screen.queryByText(/legally acknowledged/i)).toBeNull();
    expect(screen.queryByText(/legal partners/i)).toBeNull();
    // where the certificate is used
    expect(screen.getByRole("link", { name: /the claim page/i })).toHaveAttribute("href", "/estate-claim");
  });

  it("edits a person: the form opens with their record and the change is saved", async () => {
    api.update.mockResolvedValue({ ...FATIMA, full_name: "Fatima A. Mansouri", version: 3 });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Edit Fatima Mansouri" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Edit Fatima Mansouri")).toBeInTheDocument();
    const name = within(dialog).getByLabelText("Full legal name");
    expect(name).toHaveValue("Fatima Mansouri");
    expect(within(dialog).getByLabelText("ID number")).toHaveValue("A1234567");
    // the copy already on file is listed, and can be opened or removed
    expect(within(dialog).getByText("passport.jpg")).toBeInTheDocument();
    // the others hold 20%: this person can have up to 80%
    expect(within(dialog).getByText("20% allocated to others · 80% available for this person")).toBeInTheDocument();

    fireEvent.change(name, { target: { value: "Fatima A. Mansouri" } });
    fireEvent.change(within(dialog).getByLabelText("Phone"), { target: { value: "" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save Changes" }));

    await waitFor(() => expect(api.update).toHaveBeenCalledTimes(1));
    expect(api.update).toHaveBeenCalledWith("b1", {
      full_name: "Fatima A. Mansouri",
      relationship: "Daughter",
      email: "fatima@heirs.io",
      phone: null, // emptied: cleared on the record
      allocation_pct: 60,
      notes: "My eldest",
      meta: { role: "heir", idType: "Passport", idNumber: "A1234567", scope: ["ownership", "wallet"], trigger: "death" },
    });
    expect(api.add).not.toHaveBeenCalled();
    await waitFor(() => expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: "Beneficiary updated" })));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("adds a person, then uploads the copy of their identity document", async () => {
    api.add.mockResolvedValue({ ...OMAR, id: "b3", full_name: "Sara Mansouri" });
    api.addDocument.mockResolvedValue({});
    mount();
    await screen.findByTestId("beneficiary-b1");
    fireEvent.click(screen.getByRole("button", { name: /Add Beneficiary/i }));
    const dialog = await screen.findByRole("dialog");
    // the form says what its choices do: what the wallet tick adds, and that nothing moves by itself
    expect(within(dialog).getByTestId("coverage-help")).toHaveTextContent(
      /Tick Wallet Balance or Full Portfolio to add the same share of your wallet balance/,
    );
    expect(within(dialog).getByTestId("condition-help")).toHaveTextContent(
      /Nothing is transferred by itself: a transfer is made only through a claim/,
    );
    expect(within(dialog).getByText(/In Latin letters, as in their passport/)).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Full legal name"), { target: { value: "Sara Mansouri" } });
    fireEvent.change(within(dialog).getByLabelText("Relationship"), { target: { value: "Daughter" } });
    fireEvent.change(within(dialog).getByLabelText("ID number"), { target: { value: "P998877" } });

    const front = file("id-front.jpg", "image/jpeg");
    const back = file("id-back.png", "image/png");
    fireEvent.change(within(dialog).getByTestId("id-file-input"), { target: { files: [front, back] } });
    expect(within(dialog).getByText("id-front.jpg")).toBeInTheDocument();
    expect(within(dialog).getAllByText("· uploaded when you save")).toHaveLength(2);
    // one of them is taken back out before saving
    fireEvent.click(within(dialog).getByRole("button", { name: "Do not upload id-back.png" }));

    fireEvent.click(within(dialog).getByRole("button", { name: "Save Beneficiary" }));
    await waitFor(() => expect(api.addDocument).toHaveBeenCalledTimes(1));
    expect(api.add).toHaveBeenCalledWith(
      expect.objectContaining({
        full_name: "Sara Mansouri",
        relationship: "Daughter",
        email: null,
        meta: expect.objectContaining({ idNumber: "P998877", role: "beneficiary" }),
      }),
    );
    // the file goes to the record that was just created
    expect(api.addDocument).toHaveBeenCalledWith("b3", front);
    await waitFor(() => expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: "Beneficiary added" })));
  });

  it("refuses a file that is not a photo or a PDF, or is too large, before anything is uploaded", async () => {
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Edit Omar Mansouri" }));
    const dialog = await screen.findByRole("dialog");
    const input = within(dialog).getByTestId("id-file-input");
    fireEvent.change(input, { target: { files: [file("virus.exe", "application/octet-stream")] } });
    fireEvent.change(input, { target: { files: [file("huge.pdf", "application/pdf", 11 * 1024 * 1024)] } });
    expect(toast).toHaveBeenCalledTimes(2);
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: "File not added" }));
    expect(within(dialog).getByText("No copy on file yet.")).toBeInTheDocument();
    expect(api.addDocument).not.toHaveBeenCalled();
  });

  it("a saved record is not lost when one of its files cannot be uploaded", async () => {
    api.update.mockResolvedValue(OMAR);
    api.addDocument.mockRejectedValue(new ApiError("UNSUPPORTED_FILE_TYPE", "Upload a photo (JPG, PNG or WebP) or a PDF.", 415));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Edit Omar Mansouri" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByTestId("id-file-input"), { target: { files: [file("scan.pdf", "application/pdf")] } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save Changes" }));
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Saved, but a file was not uploaded",
          description: expect.stringContaining("scan.pdf: Upload a photo"),
        }),
      ),
    );
    expect(api.update).toHaveBeenCalledTimes(1);
  });

  it("downloads the person's certificate under its number", async () => {
    const pdf = new Blob(["%PDF"], { type: "application/pdf" });
    api.certificate.mockResolvedValue(pdf);
    mount();
    const card = await screen.findByTestId("beneficiary-b1");
    fireEvent.click(within(card).getByRole("button", { name: /Certificate/ }));
    await waitFor(() => expect(saveBlob).toHaveBeenCalledWith(pdf, "beneficiary-certificate-CPB-3FA4-91C2.pdf"));
    expect(api.certificate).toHaveBeenCalledWith("b1");
  });

  it("says why a certificate cannot be issued, and opens the record to complete it", async () => {
    api.certificate.mockRejectedValue(
      new ApiError("CERTIFICATE_NEEDS_ID", "Add this person's identity document number first (Edit).", 422),
    );
    mount();
    const card = await screen.findByTestId("beneficiary-b2");
    fireEvent.click(within(card).getByRole("button", { name: /Certificate/ }));
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "The certificate could not be issued",
          description: "Add this person's identity document number first (Edit).",
        }),
      ),
    );
    expect(within(await screen.findByRole("dialog")).getByText("Edit Omar Mansouri")).toBeInTheDocument();
    expect(saveBlob).not.toHaveBeenCalled();
  });

  it("asks before removing a person", async () => {
    api.remove.mockResolvedValue(undefined);
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Remove Omar Mansouri" }));
    const confirm = await screen.findByRole("alertdialog");
    expect(within(confirm).getByText("Remove Omar Mansouri?")).toBeInTheDocument();
    expect(api.remove).not.toHaveBeenCalled();
    fireEvent.click(within(confirm).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledWith("b2"));
  });

  it("a closed register cannot be changed, and its certificates still download", async () => {
    api.list.mockResolvedValue([{ ...FATIMA, locked: true }, { ...OMAR, locked: true }]);
    api.certificate.mockResolvedValue(new Blob(["%PDF"]));
    mount();
    expect(await screen.findByTestId("register-closed")).toHaveTextContent(/This register is closed/);
    expect(screen.getByRole("button", { name: /Add Beneficiary/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Edit Fatima Mansouri" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Remove Fatima Mansouri" })).toBeDisabled();
    fireEvent.click(within(screen.getByTestId("beneficiary-b1")).getByRole("button", { name: /Certificate/ }));
    await waitFor(() => expect(saveBlob).toHaveBeenCalled());
  });
});
