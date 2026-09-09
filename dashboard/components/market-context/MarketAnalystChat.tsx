"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Badge } from "@/components/ui/badge";
import type { MarketAnalystChatResponse } from "@/domain";
import { ANALYST_CHAT as L } from "@/lib/i18n/vi";
import { safeExternalHref } from "@/lib/market-context/display";
import { cn } from "@/lib/utils";
import { useMarketAnalystChat } from "@/queries/use-trading-queries";
import { ApiError } from "@/lib/api/errors";

type ChatTurn = {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: MarketAnalystChatResponse;
};

type MarketAnalystChatProps = {
  symbol: string;
  expanded?: boolean;
  onToggle?: () => void;
};

const ContextBadges = ({
  used,
}: {
  used: MarketAnalystChatResponse["usedContext"];
}) => (
  <div className="flex flex-wrap gap-1.5">
    {used.technical ? (
      <Badge variant="default">{L.badgeTechnical}</Badge>
    ) : null}
    {used.external ? (
      <Badge variant="default">{L.badgeExternal}</Badge>
    ) : null}
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

export const MarketAnalystChat = ({
  symbol,
  expanded = false,
  onToggle,
}: MarketAnalystChatProps) => {
  const mutation = useMarketAnalystChat(symbol);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [localError, setLocalError] = useState<string | null>(null);
  const [localExpanded, setLocalExpanded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevSymbol = useRef(symbol);
  const turnSeq = useRef(0);

  const isExpanded = onToggle ? expanded : localExpanded;
  const handleToggle = onToggle ?? (() => setLocalExpanded((v) => !v));

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
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [turns, mutation.isPending]);

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

  const lastAssistant = [...turns].reverse().find((t) => t.role === "assistant");
  const chatEnabled = lastAssistant?.response?.chatEnabled;
  const showDisabledHint =
    chatEnabled === false ||
    lastAssistant?.response?.warnings.includes("ai_chat_disabled");

  return (
    <section
      className="rounded-xl border border-[var(--border)] bg-[var(--surface)]"
      aria-label={L.title}
    >
      <div className="flex flex-wrap items-start justify-between gap-2 px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[14px] font-semibold text-[var(--foreground)]">
              {L.title}
            </h3>
            <span className="text-[12px] font-medium text-[var(--foreground-secondary)]">
              {symbol}
            </span>
            {lastAssistant?.response?.providerMetadata.fallbackUsed ? (
              <Badge variant="default">{L.fallbackBadge}</Badge>
            ) : null}
          </div>
          <p className="mt-1 text-[12px] text-[var(--muted)]">{L.readOnly}</p>
        </div>
        <button
          type="button"
          onClick={handleToggle}
          aria-expanded={isExpanded}
          aria-controls={`analyst-chat-body-${symbol}`}
          className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-[13px] font-semibold text-[var(--foreground-secondary)] transition-colors hover:border-[var(--accent-muted)] hover:text-[var(--accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
        >
          {isExpanded ? L.hideChat : L.showChat}
        </button>
      </div>

      {isExpanded ? (
        <div id={`analyst-chat-body-${symbol}`}>
          {showDisabledHint ? (
            <p
              className="border-y border-[var(--border)] bg-[var(--surface-subtle)] px-4 py-2 text-[12px] text-[var(--foreground-secondary)]"
              role="status"
            >
              {L.disabled} {L.disabledHint}
            </p>
          ) : (
            <div className="border-t border-[var(--border)]" />
          )}

          <div
            ref={scrollRef}
            className="max-h-[280px] min-h-[140px] space-y-3 overflow-y-auto px-4 py-3"
            aria-live="polite"
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
                    <p className="max-w-[85%] rounded-lg bg-[var(--accent-subtle)] px-3 py-2 text-[13px] text-[var(--foreground)]">
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
                  <div className="whitespace-pre-wrap rounded-lg border border-[var(--border)] bg-[var(--surface-subtle)] px-3 py-2 text-[13px] leading-relaxed text-[var(--foreground)]">
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
            className="sticky bottom-0 flex gap-2 border-t border-[var(--border)] bg-[var(--surface)] px-4 py-3"
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
                "min-w-0 flex-1 rounded-lg border border-[var(--border)] bg-[var(--surface-subtle)] px-3 py-2 text-[13px] text-[var(--foreground)]",
                "placeholder:text-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]",
                "disabled:opacity-60",
              )}
              aria-label={L.placeholder}
            />
            <button
              type="submit"
              disabled={mutation.isPending || !input.trim()}
              className="shrink-0 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[13px] font-semibold text-[var(--accent)] transition-colors hover:border-[var(--accent-muted)] hover:bg-[var(--accent-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:opacity-60"
              aria-label={L.send}
            >
              {mutation.isPending ? L.sending : L.send}
            </button>
          </form>
        </div>
      ) : null}
    </section>
  );
};
