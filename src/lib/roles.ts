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
