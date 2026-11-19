import { Badge } from "@/components/ui/badge";

// Whether a certificate's units are fully paid (client, 2026-11-18, the same on every Capimax
// platform): final, or provisional while an installment plan on the property is still being
// paid. Certificates issued before the label existed carry none and show nothing.

type Props = {
  status: string | null | undefined;
  className?: string;
};

export function CertificatePaymentBadge(props: Props) {
  const extra = props.className ? " " + props.className : "";
  if (props.status === "final") {
    return (
      <Badge className={"border-0 bg-green-500/10 text-green-700" + extra} data-testid="certificate-payment">
        FINAL · FULLY PAID
      </Badge>
    );
  }
  if (props.status === "provisional") {
    return (
      <Badge className={"border-0 bg-amber-500/10 text-amber-700" + extra} data-testid="certificate-payment">
        PROVISIONAL · INSTALLMENTS OUTSTANDING
      </Badge>
    );
  }
  return null;
}
