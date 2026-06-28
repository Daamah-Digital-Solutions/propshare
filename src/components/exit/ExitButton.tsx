import { useState } from "react";
import { Button, type ButtonProps } from "@/components/ui/button";
import { LogOut } from "lucide-react";
import { ExitFlowDialog } from "./ExitFlowDialog";
import { cn } from "@/lib/utils";

interface ExitButtonProps extends Omit<ButtonProps, "onClick"> {
  initialPositionId?: string | number;
  label?: string;
  iconOnly?: boolean;
}

export function ExitButton({
  initialPositionId,
  label = "Exit",
  iconOnly = false,
  className,
  variant = "outline",
  size,
  ...rest
}: ExitButtonProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        variant={variant}
        size={iconOnly ? "icon" : size}
        onClick={() => setOpen(true)}
        className={cn("gap-1.5", className)}
        {...rest}
      >
        <LogOut className="h-4 w-4" />
        {!iconOnly && <span>{label}</span>}
      </Button>
      <ExitFlowDialog open={open} onOpenChange={setOpen} initialPositionId={initialPositionId} />
    </>
  );
}
