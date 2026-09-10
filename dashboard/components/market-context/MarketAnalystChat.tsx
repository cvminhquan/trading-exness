"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { MessageSquare, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { MarketAnalystChatResponse } from "@/domain";
import { ANALYST_CHAT as L } from "@/lib/i18n/vi";
import { ApiError } from "@/lib/api/errors";
import { safeExternalHref } from "@/lib/market-context/display";
import { cn } from "@/lib/utils";
import { useMarketAnalystChat } from "@/queries/use-trading-queries";

type ChatTurn = {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: MarketAnalystChatResponse;
};

type MarketAnalystChatProps = {
  symbol: string;
};

const ContextBadges = ({
  used,
}: {
  used: MarketAnalystChatResponse["usedContext"];
}) => (
  <div className="flex flex-wrap gap-1.5">
    {used.technical ? <Badge variant="default">{L.badgeTechnical}</Badge> : null}
    {used.external ? <Badge variant="default">{L.badgeExternal}</Badge> : null}
    {used.synthesis ? (
      <Badge variant="default">{L.badgeSynthesis}</Badge>
    ) : null}
  </div>
);

const AnalystSources = ({
  sources,
}: {
  sources: MarketAnalystChatResponse["sources"];
}) => {
  if (sources.length === 0) return null;
  return (
    <div className="mt-2 space-y-1">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--muted)]">
        {L.sources}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {sources.map((s, index) => {
          const href = safeExternalHref(s.url);
          const label = `[${index + 1}] ${s.title || s.domain || s.sourceId}`;
          if (!href) {
            return (
              <span
                key={s.sourceId || label}
                className="rounded-md border border-[var(--border)] bg-[var(--surface-subtle)] px-2 py-1 text-[11px] text-[var(--foreground-secondary)]"
              >
                {label}
              </span>
            );
          }
          return (
            <a
              key={s.sourceId || label}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md border border-[var(--border)] bg-[var(--surface-subtle)] px-2 py-1 text-[11px] font-medium text-[var(--accent)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
              aria-label={`Mở nguồn ${label}`}
            >
              {label}
            </a>
          );
        })}
      </div>
    </div>
  );
};

/**
 * Floating corner chat widget (Tawk.to-style) — analysis only, no execution.
 */
export const MarketAnalystChat = ({ symbol }: MarketAnalystChatProps) => {
  const titleId = useId();
  const mutation = useMarketAnalystChat(symbol);
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [localError, setLocalError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const prevSymbol = useRef(symbol);
  const turnSeq = useRef(0);

  useEffect(() => {
    if (prevSymbol.current !== symbol) {
      prevSymbol.current = symbol;
      setSessionId(null);
      setTurns([]);
      setLocalError(null);
      setInput("");
    }
  }, [symbol]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !open) return;
    el.scrollTop = el.scrollHeight;
  }, [turns, mutation.isPending, open]);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
  }, [open]);

  const handleClose = () => setOpen(false);
  const handleToggle = () => setOpen((v) => !v);

  const handleSend = async (message: string) => {
    const trimmed = message.trim();
    if (!trimmed || mutation.isPending) return;
    setLocalError(null);
    turnSeq.current += 1;
    const userId = `u_${turnSeq.current}`;
    setTurns((prev) => [...prev, { id: userId, role: "user", text: trimmed }]);
    setInput("");
    try {
      const data = await mutation.mutateAsync({
        message: trimmed,
        sessionId,
      });
      setSessionId(data.sessionId);
      turnSeq.current += 1;
      setTurns((prev) => [
        ...prev,
        {
          id: data.messageId || `a_${turnSeq.current}`,
          role: "assistant",
          text: data.answer,
          response: data,
        },
      ]);
    } catch (error) {
      const msg =
        error instanceof ApiError && error.status === 429
          ? L.rateLimited
          : L.error;
      setLocalError(msg);
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    void handleSend(input);
  };

  const handleSuggestedKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    question: string,
  ) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      void handleSend(question);
    }
  };

  const handleDialogKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      handleClose();
    }
  };

  const lastAssistant = [...turns].reverse().find((t) => t.role === "assistant");
  const chatEnabled = lastAssistant?.response?.chatEnabled;
  const showDisabledHint =
    chatEnabled === false ||
    lastAssistant?.response?.warnings.includes("ai_chat_disabled");

  return (
    <div
      className="pointer-events-none fixed right-4 bottom-4 z-50 flex flex-col items-end gap-3 sm:right-5 sm:bottom-5"
      aria-live="polite"
    >
      {open ? (
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="false"
          aria-labelledby={titleId}
          tabIndex={-1}
          onKeyDown={handleDialogKeyDown}
          className={cn(
            "pointer-events-auto flex w-[min(100vw-2rem,24rem)] flex-col overflow-hidden",
            "h-[min(560px,70vh)] max-h-[70vh]",
            "rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-xl",
            "outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
          )}
        >
          <div className="flex items-start justify-between gap-3 bg-[var(--accent)] px-4 py-3 text-white">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 id={titleId} className="text-[15px] font-semibold">
                  {L.title}
                </h3>
                <span className="rounded-full bg-white/20 px-2 py-0.5 text-[11px] font-semibold">
                  {symbol}
                </span>
                {lastAssistant?.response?.providerMetadata.fallbackUsed ? (
                  <span className="rounded-full bg-white/20 px-2 py-0.5 text-[11px]">
                    {L.fallbackBadge}
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-[12px] text-white/85">{L.readOnly}</p>
            </div>
            <button
              type="button"
              onClick={handleClose}
              className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-white/15 text-white transition-colors hover:bg-white/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
              aria-label={L.closeChat}
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>

          {showDisabledHint ? (
            <p
              className="border-b border-[var(--border)] bg-[var(--surface-subtle)] px-4 py-2 text-[12px] text-[var(--foreground-secondary)]"
              role="status"
            >
              {L.disabled} {L.disabledHint}
            </p>
          ) : null}

          <div
            ref={scrollRef}
            className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3"
          >
            {turns.length === 0 ? (
              <div className="space-y-3">
                <p className="text-[13px] text-[var(--muted)]">{L.emptyHint}</p>
                <div className="flex flex-wrap gap-2">
                  {L.suggested.map((q) => (
                    <button
                      key={q}
                      type="button"
                      tabIndex={0}
                      aria-label={q}
                      disabled={mutation.isPending}
                      onClick={() => void handleSend(q)}
                      onKeyDown={(e) => handleSuggestedKeyDown(e, q)}
                      className="rounded-lg border border-[var(--border)] bg-[var(--surface-subtle)] px-2.5 py-1.5 text-left text-[12px] font-medium text-[var(--foreground-secondary)] transition-colors hover:border-[var(--accent-muted)] hover:text-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:opacity-60"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {turns.map((turn) => {
              if (turn.role === "user") {
                return (
                  <div key={turn.id} className="flex justify-end">
                    <p className="max-w-[85%] rounded-2xl rounded-br-md bg-[var(--accent)] px-3 py-2 text-[13px] text-white">
                      {turn.text}
                    </p>
                  </div>
                );
              }
              const resp = turn.response;
              return (
                <div key={turn.id} className="max-w-[95%] space-y-2">
                  {resp?.contextChanged ? (
                    <p className="text-[11px] text-[var(--warning)]" role="status">
                      {L.contextUpdated}
                    </p>
                  ) : null}
                  {resp?.warnings.includes("technical_stale") ? (
                    <p className="text-[11px] font-medium text-[var(--warning)]">
                      {L.technicalStale}
                    </p>
                  ) : null}
                  {resp?.warnings.includes("external_stale") ? (
                    <p className="text-[11px] text-[var(--muted)]">
                      {L.externalStale}
                    </p>
                  ) : null}
                  {resp ? <ContextBadges used={resp.usedContext} /> : null}
                  <div className="whitespace-pre-wrap rounded-2xl rounded-bl-md border border-[var(--border)] bg-[var(--surface-subtle)] px-3 py-2 text-[13px] leading-relaxed text-[var(--foreground)]">
                    {turn.text}
                  </div>
                  {resp ? <AnalystSources sources={resp.sources} /> : null}
                </div>
              );
            })}

            {mutation.isPending ? (
              <p className="text-[12px] text-[var(--muted)]" role="status">
                {L.thinking}
              </p>
            ) : null}
          </div>

          {localError ? (
            <p
              className="px-4 pb-2 text-[12px] text-[var(--negative)]"
              role="alert"
            >
              {localError}
            </p>
          ) : null}

          <form
            onSubmit={handleSubmit}
            className="flex gap-2 border-t border-[var(--border)] bg-[var(--surface)] px-3 py-3"
          >
            <label className="sr-only" htmlFor={`analyst-chat-input-${symbol}`}>
              {L.placeholder}
            </label>
            <input
              id={`analyst-chat-input-${symbol}`}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={L.placeholder}
              disabled={mutation.isPending}
              maxLength={3000}
              className={cn(
                "min-w-0 flex-1 rounded-full border border-[var(--border)] bg-[var(--surface-subtle)] px-3.5 py-2 text-[13px] text-[var(--foreground)]",
                "placeholder:text-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
                "disabled:opacity-60",
              )}
              aria-label={L.placeholder}
            />
            <button
              type="submit"
              disabled={mutation.isPending || !input.trim()}
              className="shrink-0 rounded-full bg-[var(--accent)] px-3.5 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-[var(--accent-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:opacity-60"
              aria-label={L.send}
            >
              {mutation.isPending ? L.sending : L.send}
            </button>
          </form>
        </div>
      ) : null}

      <button
        type="button"
        onClick={handleToggle}
        aria-expanded={open}
        aria-label={open ? L.closeChat : L.openChatAria}
        title={open ? L.closeChat : L.launcherLabel}
        className={cn(
          "pointer-events-auto relative inline-flex size-14 items-center justify-center rounded-full",
          "bg-[var(--accent)] text-white shadow-lg",
          "transition-transform hover:scale-105 hover:bg-[var(--accent-hover)]",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2",
        )}
      >
        {open ? (
          <X className="size-6" aria-hidden />
        ) : (
          <MessageSquare className="size-6" aria-hidden />
        )}
        {!open ? (
          <span
            className="absolute top-1 right-1 size-2.5 rounded-full bg-[var(--positive)] ring-2 ring-white"
            aria-hidden
            title="Online"
          />
        ) : null}
      </button>
    </div>
  );
};
