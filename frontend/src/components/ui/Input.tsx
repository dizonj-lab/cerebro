import { cn } from "@/lib/cn";
import type { InputHTMLAttributes } from "react";
import { forwardRef } from "react";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { invalid = false, className, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        "w-full rounded-md border bg-surface px-3 py-2 text-sm text-ink",
        "placeholder:text-ink-subtle",
        "transition-colors duration-150",
        "disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-ink-subtle",
        invalid ? "border-danger" : "border-line-strong hover:border-ink-subtle",
        className,
      )}
      {...props}
    />
  );
});
