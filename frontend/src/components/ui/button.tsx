import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        // white-on-dark primary, like the 21st.dev / shadcn default
        default: "bg-foreground text-background shadow-sm hover:bg-foreground/90",
        accent: "btn-shimmer hover:brightness-110",
        outline: "border border-white/10 bg-white/[0.03] text-foreground hover:bg-white/[0.08] hover:border-white/20",
        ghost: "text-muted-foreground hover:bg-white/[0.06] hover:text-foreground",
        secondary: "bg-muted text-foreground hover:bg-muted/70",
      },
      size: { default: "h-10 px-4 py-2", sm: "h-8 rounded-md px-3 text-xs", lg: "h-12 px-6 text-base", icon: "h-9 w-9" },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";
export { buttonVariants };
