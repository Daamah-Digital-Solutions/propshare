import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Briefcase, CheckCircle2, CreditCard, Loader2, User as UserIcon, Users, type LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cardsApi, type CardType } from "@/lib/api";
import { cn } from "@/lib/utils";

// PropShare cards are not issued yet (client, 2026-11-19): every place that offered to issue a
// card now reads "Coming soon · Join the Waitlist" and opens this dialog, where the member picks
// the card they want and joins the waitlist (or changes their choice). Recorded on the server;
// staff see the list in the admin panel.

type Option = { id: CardType; icon: LucideIcon; label: string; detail: string };

const INVESTOR_CARDS: Option[] = [
  { id: "personal", icon: UserIcon, label: "Personal card", detail: "Linked to your wallet and rental returns." },
  { id: "family", icon: Users, label: "Family card", detail: "Linked to a family member's allocation." },
  { id: "team", icon: Briefcase, label: "Team card", detail: "For a team member, with its own sub-wallet and limit." },
];

const ROLE_CARDS: Record<string, Option> = {
  developer: { id: "developer", icon: CreditCard, label: "Developer card", detail: "Spending from your project wallet." },
  owner: { id: "owner", icon: CreditCard, label: "Property owner card", detail: "Spending from your rental income." },
  broker: { id: "broker", icon: CreditCard, label: "Broker card", detail: "Spending from your commissions." },
  liquidity: { id: "liquidity", icon: CreditCard, label: "Liquidity provider card", detail: "Spending from your platform returns." },
};

export const WAITLIST_KEY = ["cards", "waitlist"];

/** Whether the member is on the waitlist (for the button's label). */
export function useCardWaitlist() {
  return useQuery({ queryKey: WAITLIST_KEY, queryFn: cardsApi.waitlist, retry: false });
}

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** a role dashboard offers its own card; the investor's dashboard offers three */
  role?: "developer" | "owner" | "broker" | "liquidity";
};

export function CardWaitlistDialog(props: Props) {
  const options = props.role ? [ROLE_CARDS[props.role]] : INVESTOR_CARDS;
  const queryClient = useQueryClient();
  const status = useCardWaitlist();
  const saved = status.data?.joined ? status.data.card_type : null;
  const [choice, setChoice] = useState<CardType>(options[0].id);

  useEffect(() => {
    if (!props.open) return;
    const fromSaved = options.find((o) => o.id === saved);
    setChoice(fromSaved ? fromSaved.id : options[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.open, saved]);

  const join = useMutation({
    mutationFn: (card: CardType) => cardsApi.joinWaitlist(card),
    onSuccess: (data) => {
      queryClient.setQueryData(WAITLIST_KEY, data);
      toast.success("You're on the waitlist. We will tell you as soon as cards can be requested.");
      props.onOpenChange(false);
    },
    onError: () => toast.error("Could not join the waitlist. Please try again."),
  });

  const savedOption = [...INVESTOR_CARDS, ...Object.values(ROLE_CARDS)].find((o) => o.id === saved);
  const same = saved === choice;

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="card-waitlist-dialog">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10">
              <CreditCard className="h-5 w-5 text-primary" />
            </div>
            <div className="min-w-0">
              <DialogTitle>Capimax PropShare Cards</DialogTitle>
              <Badge variant="outline" className="mt-1 border-amber-500/30 text-amber-600">
                Coming soon · Join the Waitlist
              </Badge>
            </div>
          </div>
          <DialogDescription className="pt-2">
            Cards are not issued yet. Join the waitlist with the card you want and we will tell you as
            soon as you can request it.
          </DialogDescription>
        </DialogHeader>

        {savedOption && (
          <div className="flex items-start gap-2 rounded-lg border border-success/30 bg-success/10 p-3 text-sm" data-testid="card-waitlist-joined">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
            <span>
              You're on the waitlist for the <strong>{savedOption.label}</strong>.
            </span>
          </div>
        )}

        <div className="grid gap-2" role="radiogroup" aria-label="Card">
          {options.map((o) => (
            <button
              key={o.id}
              type="button"
              role="radio"
              aria-checked={choice === o.id}
              onClick={() => setChoice(o.id)}
              className={cn(
                "flex items-center gap-3 rounded-lg border p-3 text-start transition-colors",
                choice === o.id ? "border-primary bg-primary/5" : "border-border hover:bg-muted/50",
              )}
            >
              <div className="shrink-0 rounded-md bg-primary/10 p-2">
                <o.icon className="h-4 w-4 text-primary" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold">{o.label}</div>
                <div className="text-xs text-muted-foreground">{o.detail}</div>
              </div>
              <span
                className={cn(
                  "h-4 w-4 shrink-0 rounded-full border-2",
                  choice === o.id ? "border-primary bg-primary" : "border-muted-foreground/40",
                )}
              />
            </button>
          ))}
        </div>

        <DialogFooter>
          <Button
            onClick={() => join.mutate(choice)}
            disabled={join.isPending || same}
            className="gap-2"
            data-testid="card-waitlist-join"
          >
            {join.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {same ? "You're on the waitlist" : saved ? "Update my request" : "Join the Waitlist"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type ButtonProps = {
  role?: "developer" | "owner" | "broker" | "liquidity";
};

/** The button that replaced "Issue New Card" / "Request Virtual Card". */
export function CardWaitlistButton(props: ButtonProps) {
  const [open, setOpen] = useState(false);
  const status = useCardWaitlist();
  const joined = !!status.data?.joined;
  return (
    <>
      <Button className="gap-2" variant={joined ? "outline" : "default"} onClick={() => setOpen(true)} data-testid="card-waitlist-button">
        {joined ? <CheckCircle2 className="h-4 w-4" /> : <CreditCard className="h-4 w-4" />}
        {joined ? "You're on the waitlist" : "Coming soon · Join the Waitlist"}
      </Button>
      <CardWaitlistDialog open={open} onOpenChange={setOpen} role={props.role} />
    </>
  );
}
