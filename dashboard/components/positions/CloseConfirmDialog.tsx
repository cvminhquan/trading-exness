"use client";

import { useEffect, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { UI } from "@/lib/i18n/vi";

type CloseConfirmDialogProps = {
  open: boolean;
  title: string;
  body: string;
  phrase: string;
  isPending?: boolean;
  errorMessage?: string | null;
  onCancel: () => void;
  onConfirm: (confirm: string) => void;
};

export const CloseConfirmDialog = ({
  open,
  title,
  body,
  phrase,
  isPending = false,
  errorMessage,
  onCancel,
  onConfirm,
}: CloseConfirmDialogProps) => {
  const [value, setValue] = useState("");

  useEffect(() => {
    if (open) setValue("");
  }, [open]);

  if (!open) return null;

  const canSubmit = value.trim() === phrase && !isPending;

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onCancel();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="close-position-title"
      onKeyDown={handleKeyDown}
    >
      <div className="w-full max-w-md rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5 shadow-lg">
        <h2
          id="close-position-title"
          className="text-[16px] font-semibold text-[var(--foreground)]"
        >
          {title}
        </h2>
        <p className="mt-2 text-[13px] leading-relaxed text-[var(--muted)]">{body}</p>
        <div className="mt-4">
          <Label htmlFor="close-confirm-input">{UI.closeConfirmHint(phrase)}</Label>
          <Input
            id="close-confirm-input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoComplete="off"
            autoFocus
            aria-label={UI.closeConfirmHint(phrase)}
            disabled={isPending}
          />
        </div>
        {errorMessage ? (
          <p className="mt-2 text-[13px] text-[var(--negative)]" role="alert">
            {errorMessage}
          </p>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={isPending}
          >
            {UI.cancel}
          </Button>
          <Button
            type="button"
            variant="danger"
            disabled={!canSubmit}
            onClick={() => onConfirm(phrase)}
            aria-label={UI.close}
          >
            {isPending ? UI.closing : UI.close}
          </Button>
        </div>
      </div>
    </div>
  );
};
