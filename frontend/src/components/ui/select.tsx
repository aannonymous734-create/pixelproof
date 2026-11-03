import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

/** Native <select> (keeps keyboard and mobile pickers) styled to match the inputs. */
export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement> & { wrapperClassName?: string }
>(({ className, wrapperClassName, children, ...props }, ref) => (
  <div className={cn("relative inline-flex", wrapperClassName)}>
    <select
      ref={ref}
      className={cn(
        "h-10 w-full appearance-none rounded-lg border border-white/10 bg-white/[0.03] pl-3 pr-9 text-sm text-foreground",
        "transition-colors hover:border-white/20 focus:outline-none focus:ring-2 focus:ring-primary/40",
        "[&>option]:bg-card [&>option]:text-foreground",
        className,
      )}
      {...props}
    >
      {children}
    </select>
    <ChevronDown
      size={15}
      aria-hidden
      className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground"
    />
  </div>
));
Select.displayName = "Select";
