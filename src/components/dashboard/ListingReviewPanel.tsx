/**
 * Where an owner's listing stands in our review, and what they can do about it: the message
 * from our team (changes requested / not approved), "Edit & resubmit", or "Submit for review"
 * for a draft that never reached us. Nothing is shown for a listing that is on the market.
 */
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Clock, MessageSquareWarning, Send, XCircle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PropertyCreationForm } from "@/components/developer/PropertyCreationForm";
import { ApiError, propertyApi, type PropertyDetail } from "@/lib/api";
import { isOnMarket, ownerListingStatus } from "@/lib/propertyStatus";
import { toast } from "sonner";

const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString() : "");

export function ListingReviewPanel({ property }: { property: PropertyDetail }) {
  const queryClient = useQueryClient();
  const [sending, setSending] = useState(false);
  if (isOnMarket(property.status)) return null;
  const view = ownerListingStatus(property);

  const submit = async () => {
    setSending(true);
    try {
      await propertyApi.submit(property.id);
      toast.success("Listing sent for review", {
        description: "Our team will review it and tell you the outcome here and by email.",
      });
      await queryClient.invalidateQueries({ queryKey: ["owner-properties"] });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not send it. Please try again.");
    } finally {
      setSending(false);
    }
  };

  if (property.status === "under_review") {
    return (
      <Alert className="mb-4 border-warning/40 bg-warning/10" data-testid="listing-review">
        <Clock className="h-4 w-4 text-warning" />
        <AlertTitle>Under review{property.submitted_at ? ` since ${when(property.submitted_at)}` : ""}</AlertTitle>
        <AlertDescription>
          {view.hint} You can still add documents from the{" "}
          <Link to="/owner-dashboard?tab=documents" className="underline">
            Documents
          </Link>{" "}
          tab.
        </AlertDescription>
      </Alert>
    );
  }

  if (property.status === "closed") {
    if (property.review_outcome !== "declined" && !property.review_note) return null;
    return (
      <Alert variant="destructive" className="mb-4" data-testid="listing-review">
        <XCircle className="h-4 w-4" />
        <AlertTitle>{view.label}</AlertTitle>
        {property.review_note && (
          <AlertDescription className="whitespace-pre-line">
            Message from our team: {property.review_note}
          </AlertDescription>
        )}
      </Alert>
    );
  }

  // draft: changes requested, or never sent to us
  const changesRequested = property.review_outcome === "changes_requested";
  return (
    <Alert className="mb-4 border-accent/40 bg-accent/10" data-testid="listing-review">
      <MessageSquareWarning className="h-4 w-4 text-accent" />
      <AlertTitle>{view.label}</AlertTitle>
      <AlertDescription className="space-y-3">
        {changesRequested && property.review_note && (
          <p className="whitespace-pre-line">
            <span className="font-medium">Message from our team{property.reviewed_at ? ` (${when(property.reviewed_at)})` : ""}:</span>{" "}
            {property.review_note}
          </p>
        )}
        <p>{view.hint}</p>
        <div className="flex flex-wrap gap-2">
          <PropertyCreationForm editing={property} />
          {!changesRequested && (
            <Button size="sm" variant="outline" className="gap-2" onClick={submit} disabled={sending}>
              <Send className="h-4 w-4" />
              Submit for review as is
            </Button>
          )}
        </div>
      </AlertDescription>
    </Alert>
  );
}
