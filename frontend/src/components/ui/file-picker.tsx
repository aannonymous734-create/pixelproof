import { useId, useRef } from "react";
import { FileUp, X } from "lucide-react";
import { cn } from "@/lib/utils";

/** Styled replacement for <input type="file">: shows the chosen name, with a clear button. */
export function FilePicker({
  label,
  accept,
  file,
  onChange,
  placeholder = "Choose a file…",
  className,
}: {
  label: string;
  accept?: string;
  file: File | null;
  onChange: (f: File | null) => void;
  placeholder?: string;
  className?: string;
}) {
  const id = useId();
  const ref = useRef<HTMLInputElement>(null);

  return (
    <div className={cn("min-w-0", className)}>
      <label htmlFor={id} className="mb-1.5 block text-xs font-medium text-muted-foreground">
        {label}
      </label>
      <div className="relative">
        <label
          className={cn(
            "flex h-11 cursor-pointer items-center gap-3 rounded-lg border bg-white/[0.03] pl-1.5 pr-3 text-sm transition-colors",
            "focus-within:ring-2 focus-within:ring-primary/40 hover:border-white/20",
            file ? "border-primary/30" : "border-white/10",
          )}
        >
          <input
            ref={ref}
            id={id}
            type="file"
            accept={accept}
            className="sr-only"
            onChange={(e) => onChange(e.target.files?.[0] ?? null)}
          />
          <span
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-white/10",
              file ? "bg-primary/15 text-primary" : "bg-white/[0.04] text-muted-foreground",
            )}
            aria-hidden
          >
            <FileUp size={15} />
          </span>
          <span className={cn("min-w-0 flex-1 truncate", file ? "text-foreground" : "text-muted-foreground")}>
            {file ? file.name : placeholder}
          </span>
          {!file && <span className="shrink-0 text-xs font-medium text-primary">Browse</span>}
        </label>
        {file && (
          <button
            type="button"
            aria-label={`Remove ${file.name}`}
            onClick={() => {
              if (ref.current) ref.current.value = "";
              onChange(null);
            }}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-white/[0.08] hover:text-foreground"
          >
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
