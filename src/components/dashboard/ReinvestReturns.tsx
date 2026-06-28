import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogDescription,
} from "@/components/ui/dialog";
import { RefreshCcw, Percent, TrendingUp, ArrowRight, Info } from "lucide-react";
import { useReinvest } from "@/contexts/ReinvestContext";
import { useToast } from "@/hooks/use-toast";
import { investApi } from "@/lib/api";

interface ReinvestReturnsProps {
  availableReturns?: number;
  variant?: "compact" | "full";
}

/**
 * Reinvest returns at the REAL, server-applied discount (admin-configurable
 * `reinvest_discount_pct`). The rate + available returns come from the server; the actual
 * discounted units/price are computed server-side when the purchase is confirmed on a
 * property (InvestmentCalculator → investApi.reinvest). No client-side discount math.
 */
export const ReinvestReturns = ({ availableReturns, variant = "full" }: ReinvestReturnsProps) => {
  const { setReinvestment } = useReinvest();
  const navigate = useNavigate();
  const { toast } = useToast();

  const { data: portfolio } = useQuery({ queryKey: ["portfolio", "summary"], queryFn: investApi.portfolio });
  const { data: reinvestCfg } = useQuery({
    queryKey: ["reinvest", "settings"],
    queryFn: investApi.reinvestSettings,
  });

  const returns = availableReturns ?? Number(portfolio?.total_returns ?? 0);
  const discountPct = Number(reinvestCfg?.discount_pct ?? 0);
  const [reinvestAmount, setReinvestAmount] = useState(0);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const amount = reinvestAmount || returns;

  const handleReinvest = () => {
    if (amount <= 0) {
      toast({ title: "No returns to reinvest", description: "You have no available returns yet." });
      return;
    }
    setReinvestment(amount);
    setIsDialogOpen(false);
    toast({
      title: "Reinvestment ready",
      description: `Pick a property to reinvest $${amount.toLocaleString()} — a ${discountPct}% discount is applied at purchase.`,
    });
    navigate("/marketplace");
  };

  const dialog = (
    <ReinvestDialog
      returns={returns}
      discountPct={discountPct}
      amount={amount}
      setReinvestAmount={setReinvestAmount}
      handleReinvest={handleReinvest}
    />
  );

  if (variant === "compact") {
    return (
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogTrigger asChild>
          <Button variant="outline" className="gap-2 border-primary/50 hover:border-primary hover:bg-primary/5">
            <RefreshCcw className="h-4 w-4 text-primary" />
            <span className="text-primary">Reinvest Returns</span>
            {discountPct > 0 && (
              <Badge className="bg-primary/20 text-primary border-0 ml-1">{discountPct}% OFF</Badge>
            )}
          </Button>
        </DialogTrigger>
        {dialog}
      </Dialog>
    );
  }

  return (
    <Card className="bg-gradient-to-br from-primary/10 via-card to-accent/5 border-primary/30 overflow-hidden relative">
      <CardHeader className="relative">
        <div className="flex items-center gap-3">
          <div className="h-12 w-12 bg-primary/20 rounded-xl flex items-center justify-center">
            <RefreshCcw className="h-6 w-6 text-primary" />
          </div>
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              Reinvest Returns
              {discountPct > 0 && (
                <Badge className="bg-primary text-primary-foreground">{discountPct}% Discount</Badge>
              )}
            </CardTitle>
            <p className="text-sm text-muted-foreground mt-1">
              Put your returns back to work at a discounted unit price
            </p>
          </div>
        </div>
      </CardHeader>

      <CardContent className="relative space-y-6">
        <div className="bg-card/80 backdrop-blur rounded-xl p-4 border border-border/50">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Available Returns to Reinvest</p>
              <p className="text-3xl font-bold text-foreground">${returns.toLocaleString()}</p>
            </div>
            <div className="h-14 w-14 bg-primary/10 rounded-full flex items-center justify-center">
              <TrendingUp className="h-7 w-7 text-primary" />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="bg-primary/10 rounded-xl p-3 text-center">
            <Percent className="h-5 w-5 text-primary mx-auto mb-1" />
            <p className="text-lg font-bold text-primary">{discountPct}%</p>
            <p className="text-xs text-muted-foreground">Discount Rate (server-applied)</p>
          </div>
          <div className="bg-accent/10 rounded-xl p-3 text-center">
            <TrendingUp className="h-5 w-5 text-accent mx-auto mb-1" />
            <p className="text-lg font-bold text-accent">${returns.toLocaleString()}</p>
            <p className="text-xs text-muted-foreground">Available</p>
          </div>
        </div>

        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogTrigger asChild>
            <Button className="w-full gap-2" size="lg" disabled={returns <= 0}>
              <RefreshCcw className="h-5 w-5" />
              Reinvest Returns
              <ArrowRight className="h-5 w-5" />
            </Button>
          </DialogTrigger>
          {dialog}
        </Dialog>

        <div className="flex items-start gap-2 p-3 bg-muted/50 rounded-lg">
          <Info className="h-4 w-4 text-muted-foreground flex-shrink-0 mt-0.5" />
          <p className="text-xs text-muted-foreground">
            Reinvesting buys units at a discounted price — the discount is applied by the server
            when you confirm on a property. Standard investments are at the direct price.
          </p>
        </div>
      </CardContent>
    </Card>
  );
};

interface ReinvestDialogProps {
  returns: number;
  discountPct: number;
  amount: number;
  setReinvestAmount: (amount: number) => void;
  handleReinvest: () => void;
}

const ReinvestDialog = ({ returns, discountPct, amount, setReinvestAmount, handleReinvest }: ReinvestDialogProps) => {
  return (
    <DialogContent className="sm:max-w-md">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <RefreshCcw className="h-5 w-5 text-primary" />
          Reinvest Your Returns
        </DialogTitle>
        <DialogDescription>
          Choose how much to reinvest. A {discountPct}% discount is applied server-side when you
          confirm on a property.
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-6 py-4">
        <div className="p-4 rounded-xl bg-muted/50 border border-border">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Available Returns</span>
            <span className="text-xl font-bold text-foreground">${returns.toLocaleString()}</span>
          </div>
        </div>

        <div className="space-y-4">
          <Label>Reinvestment Amount</Label>
          <Slider
            value={[amount]}
            onValueChange={([value]) => setReinvestAmount(value)}
            min={0}
            max={Math.max(returns, 0)}
            step={50}
            className="w-full"
          />
          <div className="relative">
            <span className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
            <Input
              type="number"
              value={amount}
              onChange={(e) =>
                setReinvestAmount(Math.min(Math.max(Number(e.target.value), 0), returns))
              }
              className="pl-8 text-lg font-semibold"
            />
          </div>
        </div>

        <Button onClick={handleReinvest} className="w-full gap-2" size="lg" disabled={amount <= 0}>
          Reinvest ${amount.toLocaleString()}
          <ArrowRight className="h-5 w-5" />
        </Button>

        <p className="text-xs text-center text-muted-foreground">
          You'll choose a property next; the server computes the discounted units at confirmation.
        </p>
      </div>
    </DialogContent>
  );
};
