import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";

/** Consistent page title block: small eyebrow, gradient title, one-line description, optional actions. */
export function PageHeader({
  eyebrow,
  title,
  children,
  actions,
}: {
  eyebrow?: string;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.header
      initial={reduce ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-wrap items-end justify-between gap-3"
      data-tour="page"
    >
      <div className="max-w-2xl">
        {eyebrow && (
          <div className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-primary">{eyebrow}</div>
        )}
        <h1 className="text-gradient text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
        {children && <p className="mt-2 text-sm leading-relaxed text-muted-foreground sm:text-base">{children}</p>}
      </div>
      {actions}
    </motion.header>
  );
}
