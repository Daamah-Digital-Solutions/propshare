// Exit / secondary-market data (Phase 8) — DB-backed (no more localStorage mock).
//
// Holdings come from the ownership ledger (holdingsApi); "exit requests" are the caller's
// real secondary-market listings (secondaryApi) AND their instant-exit requests to the
// liquidity providers (liquidityApi.myRequests), so an investor sees — and can cancel — a
// request that waits for a liquidity provider, and sees it paid once one funds it.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  holdingsApi,
  liquidityApi,
  secondaryApi,
  type Holding,
  type LpExitRequest,
  type SecondaryListing,
} from "@/lib/api";

export type ExitMethod = "secondary" | "liquidity";
export type ExitStatus = "listed" | "matching" | "settling" | "completed" | "cancelled";

export interface ExitRequest {
  id: string;
  propertyId: string | number;
  propertyName: string;
  propertyImage?: string;
  method: ExitMethod;
  units: number;
  pricePerUnit: number;
  estimatedProceeds: number;
  fee: number;
  netProceeds: number;
  remainingUnits: number;
  settlementEta: string;
  createdAt: string;
  status: ExitStatus;
}

export interface OwnedPosition {
  id: string;
  name: string;
  location: string;
  image?: string;
  units: number;
  unitPrice: number;
  investedPrice: number;
  type: string;
  demand: string;
  liquidity: string;
}

const LISTING_STATUS: Record<string, ExitStatus> = {
  active: "listed",
  sold: "completed",
  cancelled: "cancelled",
};

function toExitRequest(l: SecondaryListing): ExitRequest {
  const price = Number(l.price_per_unit);
  const gross = l.units_for_sale * price;
  return {
    id: l.listing_id,
    propertyId: l.property_id ?? "",
    propertyName: l.property_title ?? "Property",
    method: "secondary",
    units: l.units_for_sale,
    pricePerUnit: price,
    estimatedProceeds: gross,
    fee: 0, // seller receives the full gross; the resale fee is buyer-side
    netProceeds: gross,
    remainingUnits: l.units_remaining,
    settlementEta: l.status === "sold" ? "Settled" : "On sale",
    createdAt: l.created_at ?? new Date(0).toISOString(),
    status: LISTING_STATUS[l.status] ?? "listed",
  };
}

const LP_STATUS: Record<string, ExitStatus> = {
  open: "matching",
  filled: "completed",
  cancelled: "cancelled",
  expired: "cancelled",
};

function toLpExitRequest(r: LpExitRequest): ExitRequest {
  const net = Number(r.seller_net);
  const perUnit = r.units ? net / r.units : 0;
  // providers may fund part of a request; the rest keeps waiting until it expires
  const funded = Math.max(0, r.units - r.units_remaining);
  const partly = funded > 0 && r.status !== "filled";
  const expires = r.expires_at ? new Date(r.expires_at).toLocaleDateString() : "";
  const rest = r.status === "open" ? "the rest waits for a provider" : r.status === "expired" ? "the rest expired" : "the rest was cancelled";
  const eta =
    r.status === "filled"
      ? "Paid to your wallet"
      : partly
        ? `Partly funded: ${funded} of ${r.units} units paid to your wallet; ${rest}`
        : r.status === "open"
          ? `Waiting for a liquidity provider${expires ? ` (until ${expires})` : ""}`
          : r.status === "expired"
            ? "Expired — no provider funded it"
            : "Cancelled";
  // what was actually paid out once the request is over; the full request while it is open
  const paidNet = r.status === "open" || r.status === "filled" ? net : perUnit * funded;
  return {
    id: r.request_id,
    propertyId: r.property_id,
    propertyName: r.property_title ?? "Property",
    method: "liquidity",
    units: r.units,
    pricePerUnit: perUnit,
    estimatedProceeds: Number(r.gross),
    fee: Number(r.liquidity_fee),
    netProceeds: Math.round(paidNet * 100) / 100,
    remainingUnits: r.units_remaining,
    settlementEta: eta,
    createdAt: r.created_at ?? new Date(0).toISOString(),
    // a partly paid request that is over counts as completed (money reached the seller)
    status: partly && r.status !== "open" ? "completed" : (LP_STATUS[r.status] ?? "matching"),
  };
}

function toOwnedPosition(h: Holding): OwnedPosition {
  const price = Number(h.unit_price);
  return {
    id: h.property_id,
    name: h.title ?? "Property",
    location: h.location ?? "—",
    units: h.sellable_units,
    unitPrice: price,
    investedPrice: price,
    type: "Ownership",
    demand: "—",
    liquidity: "—",
  };
}

/** The caller's real exit requests: secondary-market listings + instant exits to the LPs. */
export function useExitRequests(): ExitRequest[] {
  const { data } = useQuery({
    queryKey: ["secondary", "mine"],
    queryFn: () => secondaryApi.mine(),
  });
  const { data: lp } = useQuery({
    queryKey: ["liquidity", "mine"],
    queryFn: () => liquidityApi.myRequests(),
  });
  return [...(data?.items ?? []).map(toExitRequest), ...(lp?.items ?? []).map(toLpExitRequest)].sort(
    (a, b) => b.createdAt.localeCompare(a.createdAt),
  );
}

/** The caller's net holdings (sellable units), shaped as positions for the exit flow. */
export function useOwnedPositions(): OwnedPosition[] {
  const { data } = useQuery({
    queryKey: ["secondary", "holdings"],
    queryFn: () => holdingsApi.mine(),
  });
  return (data?.items ?? []).filter((h) => h.sellable_units > 0).map(toOwnedPosition);
}

/** Cancel one of the caller's open exit requests (a listing, or an instant exit to the LPs). */
export function useCancelExitRequest() {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: async (r: Pick<ExitRequest, "id" | "method">): Promise<{ status: string }> =>
      r.method === "liquidity" ? liquidityApi.cancelRequest(r.id) : secondaryApi.cancel(r.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["secondary"] });
      qc.invalidateQueries({ queryKey: ["liquidity"] });
    },
  });
  return (r: Pick<ExitRequest, "id" | "method">) => m.mutate(r);
}

/** Create a real secondary-market listing (the secondary-exit path). */
export function useCreateListing() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { property_id: string; units: number; price_per_unit: number }) =>
      secondaryApi.create(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["secondary"] }),
  });
}

/** Create a real LP instant-exit request (the liquidity-provider exit path). */
export function useCreateExitRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { property_id: string; units: number }) =>
      liquidityApi.createExitRequest(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["secondary"] });
      qc.invalidateQueries({ queryKey: ["liquidity"] });
    },
  });
}
