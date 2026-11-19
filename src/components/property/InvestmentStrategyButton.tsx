import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

// "Investment Strategy" on the property page (client, 2026-11-19): a button that opens a fixed
// text chosen by the property's registered type, ready or under construction.

type Props = {
  ready: boolean;
};

export function InvestmentStrategyButton(props: Props) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 gap-1.5 rounded-full px-3 text-xs" data-testid="investment-strategy">
          <Compass className="h-3.5 w-3.5" />
          Investment Strategy
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Compass className="h-5 w-5 text-primary" />
            Investment Strategy
          </DialogTitle>
          <DialogDescription>{props.ready ? "Ready Property" : "Under Construction"}</DialogDescription>
        </DialogHeader>
        {props.ready ? (
          <p className="leading-relaxed text-foreground" data-testid="investment-strategy-text">
            The strategy focuses on the potential rental income from operating the property, together
            with the opportunities for its price to rise and for its value to grow and change over time.
          </p>
        ) : (
          <p className="leading-relaxed text-foreground" data-testid="investment-strategy-text">
            The strategy focuses on the opportunities for the property's value to grow and change as
            construction advances, until it is complete. The investor reviews the construction
            milestones and the installment schedule when one is available, and the opportunity's
            details set out the handover dates and the exit options available.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
