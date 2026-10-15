import { cn } from "@/lib/cn";
import type { SelectHTMLAttributes } from "react";

export function Select({
  className,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink",
        "transition-colors duration-150 hover:border-ink-subtle",
        "disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-ink-subtle",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}
