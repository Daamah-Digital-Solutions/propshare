import { useQuery } from "@tanstack/react-query";
import { cryptoApi, type CryptoCoin } from "@/lib/api";

/**
 * The coins a crypto payment can be made in (the ones switched on in the platform's account),
 * shared by the picker and by every place that names a chosen coin.
 */
export function useCryptoCoins(enabled = true) {
  return useQuery({
    queryKey: ["crypto-coins"],
    queryFn: () => cryptoApi.coins(),
    staleTime: 10 * 60_000,
    enabled,
  });
}

/**
 * The smallest payment the chosen coin takes right now, and whether `amount` is under it
 * (USDT on Tron asked for 12 USD on 2026-10-06 while members were trying 3 and 4: said under
 * the coin, not learnt from a refusal). Unknown (still loading, or the provider does not say):
 * `minimum` is null and nothing is held back; the server has the last word either way.
 */
export function useCryptoMinimum(code: string | null, amount?: number) {
  const { data } = useQuery({
    queryKey: ["crypto-minimum", code],
    queryFn: () => cryptoApi.minimum(code as string),
    enabled: Boolean(code),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const minimum = data?.minimum != null ? Number(data.minimum) : null;
  const below =
    minimum !== null && Number.isFinite(minimum) && amount !== undefined && amount > 0
      ? amount < minimum
      : false;
  return { minimum, below };
}

// The provider names a network by a short code; the ones members meet most, in words.
const NETWORKS: Record<string, string> = {
  TRX: "Tron",
  BSC: "BNB Smart Chain (BSC)",
  ETH: "Ethereum",
  SOL: "Solana",
  MATIC: "Polygon",
  ARBITRUM: "Arbitrum",
  ARB: "Arbitrum",
  OP: "Optimism",
  BASE: "Base",
  AVAXC: "Avalanche C-Chain",
  TON: "TON",
  BTC: "Bitcoin",
  LTC: "Litecoin",
  DOGE: "Dogecoin",
  XRP: "XRP Ledger",
};

/** "Tron" for TRX; a code that is not listed is shown as it is. */
export const networkName = (network: string): string => NETWORKS[network.toUpperCase()] ?? network;

/**
 * The coin's name, with its network when the provider's own name leaves it out. Most tokens
 * carry it ("Tether USD (Tron)"); some do not ("First Digital USD" is on Ethereum, "DAIARB" on
 * Arbitrum: seen in the account's list, 2026-10-06), and a member must never pick a row
 * without knowing which network it means. A network's own coin (BTC, ETH, TRX) needs none.
 */
export const coinName = (coin: CryptoCoin): string => {
  const network = coin.network?.toUpperCase();
  if (!network || coin.name.includes("(") || network === coin.ticker.toUpperCase()) {
    return coin.name;
  }
  return `${coin.name} (${networkName(network).replace(/\s*\(.*\)$/, "")})`;
};

/** "USDT · Tether USD (Tron)" */
export const coinLabel = (coin: CryptoCoin): string => `${coin.ticker} · ${coinName(coin)}`;
