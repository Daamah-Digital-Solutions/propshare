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

/** "USDT · Tether USD (Tron)" */
export const coinLabel = (coin: CryptoCoin): string => `${coin.ticker} · ${coin.name}`;

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
