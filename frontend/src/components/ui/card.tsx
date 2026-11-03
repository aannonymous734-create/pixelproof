import * as React from "react";
import { cn } from "@/lib/utils";

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** cursor-following glow (default on); turn off for large static panels */
  spotlight?: boolean;
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, spotlight = true, onMouseMove, ...props }, ref) => {
    const track = (e: React.MouseEvent<HTMLDivElement>) => {
      const r = e.currentTarget.getBoundingClientRect();
      e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
      e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
      onMouseMove?.(e);
    };
    return (
      <div
        ref={ref}
        onMouseMove={spotlight ? track : onMouseMove}
        className={cn(
          "relative overflow-hidden rounded-xl border border-white/[0.08] bg-card/70 text-card-foreground ring-hairline backdrop-blur-sm",
          spotlight && "spotlight",
          className,
        )}
        {...props}
      />
    );
  },
);
Card.displayName = "Card";

export const CardHeader = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("flex flex-col space-y-1 p-5 pb-2", className)} {...p} />
);
export const CardTitle = ({ className, ...p }: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h3 className={cn("text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground", className)} {...p} />
);
export const CardContent = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("p-5 pt-3", className)} {...p} />
);
