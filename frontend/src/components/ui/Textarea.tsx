import { cn } from "@/lib/cn";
import type { TextareaHTMLAttributes } from "react";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

export function Textarea({ invalid = false, className, ...props }: TextareaProps) {
  return (
    <textarea
      aria-invalid={invalid || undefined}
      className={cn(
        "w-full resize-y rounded-md border bg-surface px-3 py-2 text-sm text-ink",
        "placeholder:text-ink-subtle transition-colors duration-150",
        "disabled:cursor-not-allowed disabled:bg-surface-subtle",
        invalid ? "border-danger" : "border-line-strong hover:border-ink-subtle",
        className,
      )}
      {...props}
    />
  );
}
