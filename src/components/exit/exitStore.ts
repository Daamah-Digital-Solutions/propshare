// Exit / secondary-market data (Phase 8) — DB-backed (no more localStorage mock).
//
// Holdings come from the ownership ledger (holdingsApi); "exit requests" are the
// caller's real secondary-market listings (secondaryApi). The old localStorage seed
// + mock ownedPositions are retired.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  holdingsApi,
  liquidityApi,
  secondaryApi,
  type Holding,
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

/** The caller's real secondary-market listings, shaped as exit requests. */
export function useExitRequests(): ExitRequest[] {
  const { data } = useQuery({
    queryKey: ["secondary", "mine"],
    queryFn: () => secondaryApi.mine(),
  });
  return (data?.items ?? []).map(toExitRequest);
}

/** The caller's net holdings (sellable units), shaped as positions for the exit flow. */
export function useOwnedPositions(): OwnedPosition[] {
  const { data } = useQuery({
    queryKey: ["secondary", "holdings"],
    queryFn: () => holdingsApi.mine(),
  });
  return (data?.items ?? []).filter((h) => h.sellable_units > 0).map(toOwnedPosition);
}

/** Cancel one of the caller's active listings. */
export function useCancelExitRequest() {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: (id: string) => secondaryApi.cancel(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["secondary"] }),
  });
  return (id: string) => m.mutate(id);
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
