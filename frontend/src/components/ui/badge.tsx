import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium tracking-tight",
  {
    variants: {
      tone: {
        ok: "border-verdict-ok/25 bg-verdict-ok/10 text-verdict-ok",
        warn: "border-verdict-warn/25 bg-verdict-warn/10 text-verdict-warn",
        bad: "border-verdict-bad/30 bg-verdict-bad/10 text-verdict-bad",
        info: "border-verdict-info/25 bg-verdict-info/10 text-verdict-info",
        mute: "border-white/10 bg-white/[0.04] text-verdict-mute",
        outline: "border-white/10 text-foreground",
      },
    },
    defaultVariants: { tone: "outline" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
export { badgeVariants };
