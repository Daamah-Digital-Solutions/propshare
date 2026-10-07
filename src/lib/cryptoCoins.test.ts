/**
 * A coin is always named with its network. The provider's own name carries it for most tokens
 * ("Tether USD (Tron)") but not for all: the account's list on 2026-10-06 had "First Digital
 * USD" (on Ethereum) and "DAIARB" (DAI on Arbitrum), two rows a member could not tell from the
 * same coin on another network.
 */
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({ cryptoApi: { coins: vi.fn() } }));

import { coinLabel, coinName, networkName } from "./cryptoCoins";

const coin = (code: string, ticker: string, name: string, network: string | null) => ({
  code,
  ticker,
  name,
  network,
  stable: false,
  popular: false,
  memo: false,
});

describe("how a coin is named", () => {
  it("keeps the provider's name when it already says the network", () => {
    expect(coinLabel(coin("usdttrc20", "USDT", "Tether USD (Tron)", "TRX"))).toBe(
      "USDT · Tether USD (Tron)",
    );
    expect(coinLabel(coin("bnbbsc", "BNB", "Binance Coin (BSC)", "BSC"))).toBe(
      "BNB · Binance Coin (BSC)",
    );
  });

  it("adds the network, in words, when the name leaves it out", () => {
    expect(coinLabel(coin("fdusderc20", "FDUSD", "First Digital USD", "ETH"))).toBe(
      "FDUSD · First Digital USD (Ethereum)",
    );
    expect(coinLabel(coin("daiarb", "DAI", "DAIARB", "ARBITRUM"))).toBe("DAI · DAIARB (Arbitrum)");
    // no nested brackets, and a network that is not listed keeps its code
    expect(coinName(coin("fdusdbsc", "FDUSD", "First Digital USD", "bsc"))).toBe(
      "First Digital USD (BNB Smart Chain)",
    );
    expect(coinName(coin("xyznew", "XYZ", "Some Token", "NEWNET"))).toBe("Some Token (NEWNET)");
  });

  it("adds nothing for a network's own coin, or when the network is not known", () => {
    expect(coinLabel(coin("btc", "BTC", "Bitcoin", "BTC"))).toBe("BTC · Bitcoin");
    expect(coinLabel(coin("eth", "ETH", "Ethereum", "eth"))).toBe("ETH · Ethereum");
    expect(coinLabel(coin("trx", "TRX", "Tron", "TRX"))).toBe("TRX · Tron");
    expect(coinLabel(coin("usdtbsc", "USDTBSC", "USDTBSC", null))).toBe("USDTBSC · USDTBSC");
  });

  it("says a network in words for the notice", () => {
    expect(networkName("trx")).toBe("Tron");
    expect(networkName("BSC")).toBe("BNB Smart Chain (BSC)");
    expect(networkName("NEWNET")).toBe("NEWNET");
  });
});
