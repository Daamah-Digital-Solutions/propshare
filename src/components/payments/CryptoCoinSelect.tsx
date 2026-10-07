import { useMemo, useState } from "react";
import { Info, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type CryptoCoin } from "@/lib/api";
import {
  coinLabel,
  coinName,
  networkName,
  useCryptoCoins,
  useCryptoMinimum,
} from "@/lib/cryptoCoins";

/**
 * Paying in crypto: the member picks the coin and its network HERE, and the payment page is
 * then made for that one coin (client, 2026-10-06: the provider's own coin list came up empty
 * for him, and a transfer in another coin than the one picked there was not credited).
 *
 * The coins are the ones switched on in the platform's account. Stablecoins and the popular
 * coins are listed; any other is found by searching.
 */

export type CryptoPurpose = "deposit" | "purchase" | "plan";

const matches = (coin: CryptoCoin, query: string): boolean =>
  [coin.ticker, coin.name, coin.code, coin.network ?? "", coin.network ? networkName(coin.network) : ""]
    .join(" ")
    .toLowerCase()
    .includes(query);

const AFTER: Record<CryptoPurpose, string> = {
  deposit:
    "Your wallet is credited automatically once the network confirms the transfer, usually within minutes.",
  // a payment a hair short still buys (the platform's tolerance); the member is told the rule
  // that matters to them, not its size
  purchase:
    "Your units are confirmed automatically once the network confirms the transfer, usually within minutes. Send the full amount: if what arrives is clearly less, the purchase is not completed and it goes to your wallet instead.",
  plan:
    "Your plan starts automatically once the network confirms the transfer, usually within minutes. Send the full down payment: if what arrives is clearly less, the plan does not start and it goes to your wallet instead.",
};

/** What the member must know before leaving for the payment page. */
export function CryptoPayNotice({ coin, purpose }: { coin: CryptoCoin; purpose: CryptoPurpose }) {
  return (
    <div
      className="rounded-lg border border-border bg-muted/30 p-3 text-xs leading-relaxed text-muted-foreground"
      data-testid="crypto-pay-notice"
    >
      <div className="mb-1 flex items-center gap-1.5 text-sm font-medium text-foreground">
        <Info className="h-4 w-4 text-primary" /> Paying with {coin.ticker}
      </div>
      <ul className="list-disc space-y-1 pl-4">
        <li>
          The next page shows one address and the exact amount. Send{" "}
          <span className="font-medium text-foreground">
            {coin.ticker}
            {coin.network ? ` on the ${networkName(coin.network)} network` : ""}
          </span>{" "}
          only: another coin or network is credited at the value that arrives and can take
          longer.
        </li>
        {coin.memo && (
          <li>
            This coin needs the memo / tag shown on that page as well as the address. A transfer
            without it cannot be matched to you.
          </li>
        )}
        <li>
          You can close the page after sending. {AFTER[purpose]} You are notified here, and by
          email unless you turned those emails off.
        </li>
      </ul>
    </div>
  );
}

/**
 * The smallest payment the chosen coin takes right now, said before the member presses
 * anything; in red when what they are about to pay is under it. Nothing when it is not known.
 */
function CryptoMinimumHint({ coin, amount }: { coin: CryptoCoin; amount?: number }) {
  const { minimum, below } = useCryptoMinimum(coin.code, amount);
  if (minimum === null) return null;
  const least = `$${minimum.toFixed(2)}`;
  if (below && amount !== undefined) {
    return (
      <p
        role="alert"
        data-testid="crypto-minimum"
        className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
      >
        {coinLabel(coin)} takes no less than about {least} right now, and this payment is $
        {amount.toFixed(2)}. Choose another coin or a larger amount.
      </p>
    );
  }
  return (
    <p data-testid="crypto-minimum" className="text-xs text-muted-foreground">
      Smallest payment in this coin right now: about {least}.
    </p>
  );
}

interface Props {
  /** the chosen coin's code, or null */
  value: string | null;
  onChange: (code: string | null) => void;
  purpose: CryptoPurpose;
  /** what is about to be paid, in USD: checked against the chosen coin's smallest payment */
  amount?: number;
}

export function CryptoCoinSelect({ value, onChange, purpose, amount }: Props) {
  const { data, isLoading, isError, refetch } = useCryptoCoins();
  const [query, setQuery] = useState("");
  const coins = useMemo(() => data?.items ?? [], [data]);
  const chosen = coins.find((c) => c.code === value) ?? null;

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q) return [{ title: "Matching coins", items: coins.filter((c) => matches(c, q)) }];
    const stable = coins.filter((c) => c.stable);
    const popular = coins.filter((c) => c.popular && !c.stable);
    // an account whose coins carry no such marks: list them all
    if (stable.length + popular.length === 0) return [{ title: "Coins", items: coins }];
    return [
      { title: "Stablecoins", items: stable },
      { title: "Popular", items: popular },
    ].filter((g) => g.items.length > 0);
  }, [coins, query]);
  const shown = groups.reduce((n, g) => n + g.items.length, 0);

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading the coins…</p>;
  }
  if (isError || coins.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
        The coins could not be loaded right now.{" "}
        <button type="button" className="text-primary underline underline-offset-4" onClick={() => refetch()}>
          Try again
        </button>
        , or choose another payment method.
      </div>
    );
  }

  if (chosen) {
    return (
      <div className="space-y-3" data-testid="crypto-coin-select">
        <div className="flex items-center justify-between gap-3 rounded-lg border border-primary bg-primary/5 p-3">
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">You will pay with</div>
            {/* never cut short: the network is at the end of the name */}
            <div className="break-words font-medium text-foreground">{coinLabel(chosen)}</div>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={() => onChange(null)}>
            Change
          </Button>
        </div>
        <CryptoMinimumHint coin={chosen} amount={amount} />
        <CryptoPayNotice coin={chosen} purpose={purpose} />
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="crypto-coin-select">
      <div className="text-sm font-medium text-foreground">Choose the coin you will send</div>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          aria-label="Search coins"
          placeholder="Search, e.g. USDT, BTC, Tron"
          className="pl-9"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <div
        className="max-h-56 overflow-y-auto rounded-lg border border-border"
        role="listbox"
        aria-label="Coins"
      >
        {shown === 0 && (
          <p className="p-3 text-sm text-muted-foreground">No coin matches “{query.trim()}”.</p>
        )}
        {groups.map((group) =>
          group.items.length === 0 ? null : (
            <div key={group.title}>
              <div className="sticky top-0 bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
                {group.title}
              </div>
              {group.items.map((coin) => (
                <button
                  key={coin.code}
                  type="button"
                  role="option"
                  aria-selected={false}
                  onClick={() => {
                    onChange(coin.code);
                    setQuery("");
                  }}
                  className="block w-full break-words px-3 py-2 text-left text-sm hover:bg-primary/5 focus-visible:bg-primary/5 focus-visible:outline-none"
                >
                  <span className="font-medium text-foreground">{coin.ticker}</span>
                  <span className="text-muted-foreground"> · {coinName(coin)}</span>
                </button>
              ))}
            </div>
          ),
        )}
      </div>
      {!query.trim() && shown < coins.length && (
        <p className="text-xs text-muted-foreground">
          {coins.length} coins are accepted. Search to find any other.
        </p>
      )}
    </div>
  );
}

export default CryptoCoinSelect;
