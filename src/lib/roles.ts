// Self-serve role acquisition (Scenario B / D12):
//   - investor: default on every account (not requestable).
//   - owner:    self-serve — granted instantly via POST /auth/roles/request.
//   - broker / liquidity_provider: admin-approved — request creates a pending
//     role_grant_request for the admin queue.
//   - admin: never self-serve — not offered in the UI at all.

export type RequestableRole = "owner" | "broker" | "liquidity_provider";

export interface RoleOption {
  role: RequestableRole;
  label: string;
  kind: "self-serve" | "approval";
  description: string;
}

const ALL_OPTIONS: RoleOption[] = [
  {
    role: "owner",
    label: "Property Owner",
    kind: "self-serve",
    description: "List and manage properties. Granted instantly.",
  },
  {
    role: "broker",
    label: "Broker",
    kind: "approval",
    description: "Refer investors and earn commissions. Requires admin approval.",
  },
  {
    role: "liquidity_provider",
    label: "Liquidity Provider",
    kind: "approval",
    description: "Provide instant-exit liquidity. Requires admin approval.",
  },
];

/** Roles the user can still request, given the roles they already hold. */
export function requestableRoles(current: string[]): RoleOption[] {
  return ALL_OPTIONS.filter((o) => !current.includes(o.role));
}

const ROLE_LABELS: Record<string, string> = {
  investor: "Investor",
  owner: "Property Owner",
  broker: "Broker",
  liquidity_provider: "Liquidity Provider",
  admin: "Admin",
  guest: "Guest",
};

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

// --- Task 12: Broker / Liquidity-Provider join-form specs ------------------- //
export interface RoleField {
  name: string;
  label: string;
  type: "text" | "tel" | "textarea" | "select";
  required?: boolean;
  options?: string[];
  placeholder?: string;
}

export interface RoleDoc {
  name: string;
  label: string;
  required?: boolean;
  hint?: string;
}

export interface RoleApplicationSpec {
  role: "broker" | "liquidity_provider";
  title: string;
  intro: string;
  fields: RoleField[];
  documents: RoleDoc[];
}

export const ROLE_APPLICATIONS: Record<string, RoleApplicationSpec> = {
  broker: {
    role: "broker",
    title: "Become a Broker",
    intro:
      "Refer investors and earn commission on the platform fees they generate. Submit your details below — our team reviews every broker application before activation.",
    fields: [
      { name: "full_name", label: "Full / company name", type: "text", required: true },
      {
        name: "license_number",
        label: "Brokerage / real-estate license number",
        type: "text",
        required: true,
      },
      { name: "phone", label: "Contact phone", type: "tel", required: true },
      { name: "country", label: "Country of registration", type: "text", required: true },
    ],
    documents: [
      { name: "id", label: "Government ID", required: true, hint: "Passport or national ID" },
      { name: "license", label: "Brokerage / real-estate license", required: true },
    ],
  },
  liquidity_provider: {
    role: "liquidity_provider",
    title: "Become a Liquidity Provider",
    intro:
      "Provide instant-exit liquidity to investors and earn on the spread. Liquidity Providers are vetted for source of funds and standing before activation.",
    fields: [
      { name: "entity_name", label: "Name / entity name", type: "text", required: true },
      {
        name: "entity_type",
        label: "Entity type",
        type: "select",
        required: true,
        options: ["Individual", "Institution"],
      },
      { name: "jurisdiction", label: "Jurisdiction", type: "text", required: true },
      {
        name: "capital_commitment",
        label: "Intended liquidity commitment",
        type: "select",
        required: true,
        options: ["$10k – $50k", "$50k – $250k", "$250k – $1M", "$1M+"],
      },
      {
        name: "accreditation",
        label: "Investor status",
        type: "select",
        required: true,
        options: ["Retail", "Accredited", "Qualified / Professional", "Institutional"],
      },
      {
        name: "source_of_funds",
        label: "Source of funds",
        type: "textarea",
        required: true,
        placeholder: "Briefly describe the origin of the capital you'll deploy.",
      },
      { name: "phone", label: "Contact phone", type: "tel", required: true },
    ],
    documents: [
      { name: "proof_of_funds", label: "Proof of funds / bank statement", required: true },
      { name: "id", label: "Government ID", required: true, hint: "Passport or national ID" },
      {
        name: "entity_registration",
        label: "Entity registration",
        required: false,
        hint: "Required for institutions",
      },
    ],
  },
};

export const applicationRoles = () => Object.keys(ROLE_APPLICATIONS);
