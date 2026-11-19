/**
 * Trading and liquidity fees (client, 2026-11-18, the market fees letter): the same arithmetic
 * as the server's market_fees, to show each party its figures before it confirms.
 *
 *   deal                                   seller   buyer   platform   liquidity provider
 *   ordinary secondary-market sale          0.5%     1.5%     2%         —
 *   a provider buys through the LP market   1.5%     0%       1%         0.5% (of the seller fee)
 *   a provider resells those units          0%       1.5%     1%         0.5% (of the buyer fee)
 *
 * The rates come from the server's settings; the server's figures are the ones charged.
 */

/** Half-up to the cent, as the server rounds. */
export const cents = (n: number): number => Math.round((n + Number.EPSILON) * 100) / 100;
const pctOf = (amount: number, pct: number): number => (amount > 0 && pct > 0 ? cents((amount * pct) / 100) : 0);

export interface SecondaryFees {
  gross: number;
  buyerFee: number;
  sellerFee: number;
  lpUnits: number;
  lpFeeShare: number;
  totalCharged: number;
  sellerNet: number;
}

export function secondaryFees(p: {
  gross: number;
  units: number;
  lpUnits?: number;
  buyerPct: number;
  sellerPct: number;
  sharePct: number;
}): SecondaryFees {
  const gross = cents(p.gross);
  const lpUnits = Math.max(0, Math.min(p.lpUnits ?? 0, p.units));
  const lpGross = p.units > 0 ? cents((gross * lpUnits) / p.units) : 0;
  const buyerFee = pctOf(gross, p.buyerPct);
  const sellerFee = pctOf(gross - lpGross, p.sellerPct);
  const lpFeeShare = Math.min(pctOf(lpGross, p.sharePct), pctOf(lpGross, p.buyerPct));
  return {
    gross,
    buyerFee,
    sellerFee,
    lpUnits,
    lpFeeShare,
    totalCharged: cents(gross + buyerFee),
    sellerNet: cents(gross - sellerFee + lpFeeShare),
  };
}

export interface LiquidityFees {
  deal: number;
  sellerFee: number;
  lpFeeShare: number;
  sellerNet: number;
}

export function liquidityFees(p: { deal: number; feePct: number; sharePct: number }): LiquidityFees {
  const deal = cents(p.deal);
  const sellerFee = pctOf(deal, p.feePct);
  const lpFeeShare = Math.min(pctOf(deal, p.sharePct), sellerFee);
  return { deal, sellerFee, lpFeeShare, sellerNet: cents(deal - sellerFee) };
}
