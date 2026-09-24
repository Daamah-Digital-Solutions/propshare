import { useEffect, useState, type FormEvent } from "react";
import { useLocation } from "react-router-dom";
import { loadStripe, type Stripe } from "@stripe/stripe-js";
import { Elements, PaymentElement, useElements, useStripe } from "@stripe/react-stripe-js";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ApiError, paymentMethodsApi } from "@/lib/api";
import { toast } from "sonner";

// Stripe.js is loaded once per publishable key (the key comes from the server, so it is only
// known at runtime); reopening the dialog reuses it. A failed load is forgotten so the next
// open tries again (a flaky network or a blocked script must not stick until a reload).
const stripeByKey = new Map<string, Promise<Stripe | null>>();
function stripeFor(publishableKey: string): Promise<Stripe | null> {
  let stripe = stripeByKey.get(publishableKey);
  if (!stripe) {
    stripe = loadStripe(publishableKey);
    stripeByKey.set(publishableKey, stripe);
    stripe.then(
      (loaded) => {
        if (!loaded) stripeByKey.delete(publishableKey);
      },
      () => stripeByKey.delete(publishableKey),
    );
  }
  return stripe;
}

function describe(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback;
}

interface CardSetupFormProps {
  onSaved: () => void;
  onBusyChange: (busy: boolean) => void;
}

function CardSetupForm({ onSaved, onBusyChange }: CardSetupFormProps) {
  const stripe = useStripe();
  const elements = useElements();
  const { pathname } = useLocation();
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  // Once Stripe has saved the card, a failed step on our side is retried on its own: the card
  // is not entered or confirmed again (Stripe refuses a second confirm of the same setup).
  const [confirmedSetup, setConfirmedSetup] = useState<string | null>(null);

  useEffect(() => onBusyChange(saving), [saving, onBusyChange]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!stripe || !elements) return;
    setSaving(true);
    setProblem(null);
    let setupId = confirmedSetup;
    if (!setupId) {
      // The card goes straight from Stripe's form to Stripe; we only ever see the result. After a
      // bank check (3-D Secure) Stripe may come back to this same dashboard page.
      const { error, setupIntent } = await stripe.confirmSetup({
        elements,
        confirmParams: { return_url: `${window.location.origin}${pathname}?tab=wallet` },
        redirect: "if_required",
      });
      const done =
        setupIntent ??
        (error?.code === "setup_intent_unexpected_state" &&
        error.setup_intent?.status === "succeeded"
          ? error.setup_intent
          : undefined);
      if (!done) {
        setProblem(error?.message ?? "Your card could not be saved.");
        setSaving(false);
        return;
      }
      setupId = done.id;
      setConfirmedSetup(setupId);
    }
    try {
      await paymentMethodsApi.add(setupId); // idempotent on the server
      toast.success("Card saved");
      onSaved();
    } catch (e) {
      setProblem(describe(e, "Your card could not be saved."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      {/* a card, nothing else: Checkout never lists saved wallets (Apple Pay, Google Pay, Link) */}
      <PaymentElement
        options={{ wallets: { applePay: "never", googlePay: "never", link: "never" } }}
        onReady={() => setReady(true)}
        onLoadError={(e) =>
          setProblem(e.error?.message ?? "Stripe's card form could not load. Please try again later.")
        }
      />
      {problem && (
        <p role="alert" className="text-sm text-destructive">
          {problem}
        </p>
      )}
      <Button
        type="submit"
        className="w-full"
        disabled={!stripe || saving || (!ready && !confirmedSetup)}
      >
        {saving ? "Saving…" : confirmedSetup ? "Try again" : "Save card"}
      </Button>
    </form>
  );
}

interface AddCardDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}

/** Add a card through Stripe's own secure form (Payment Element on a SetupIntent). The card
 * number never touches our servers; the backend reads the saved card from Stripe. */
export function AddCardDialog({ open, onOpenChange, onSaved }: AddCardDialogProps) {
  const [setup, setSetup] = useState<{ clientSecret: string; publishableKey: string } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) {
      setSetup(null);
      setBusy(false);
      return;
    }
    let cancelled = false;
    (async () => {
      let started;
      try {
        started = await paymentMethodsApi.setupIntent();
      } catch (e) {
        if (cancelled) return;
        onOpenChange(false);
        if (e instanceof ApiError && e.status === 503) {
          toast.info("Saving cards isn't available yet", {
            description: "You can still pay by card on Stripe's secure page when you deposit.",
          });
        } else {
          toast.error(describe(e, "Could not start adding a card."));
        }
        return;
      }
      // Load Stripe's script before showing the form, so a failure is said, not a blank box.
      const loaded = await stripeFor(started.publishable_key).catch(() => null);
      if (cancelled) return;
      if (!loaded) {
        onOpenChange(false);
        toast.error("Stripe's secure card form could not load. Check your connection and try again.");
        return;
      }
      setSetup({ clientSecret: started.client_secret, publishableKey: started.publishable_key });
    })();
    return () => {
      cancelled = true;
    };
    // onOpenChange is the parent's state setter; re-running on its identity would re-create setups
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <Dialog
      open={open}
      // not while the card is being saved: the answer would land on a closed form
      onOpenChange={(next) => {
        if (next || !busy) onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add a card</DialogTitle>
          <DialogDescription>
            Your card is entered in Stripe's secure form and stored by Stripe. We never see or keep
            the card number.
          </DialogDescription>
        </DialogHeader>
        {setup ? (
          <Elements
            key={setup.clientSecret} // Stripe's options are fixed once mounted: one per setup
            stripe={stripeFor(setup.publishableKey)}
            options={{ clientSecret: setup.clientSecret, appearance: { theme: "stripe" } }}
          >
            <CardSetupForm onSaved={onSaved} onBusyChange={setBusy} />
          </Elements>
        ) : (
          <p className="text-sm text-muted-foreground">Opening Stripe's secure card form…</p>
        )}
      </DialogContent>
    </Dialog>
  );
}
