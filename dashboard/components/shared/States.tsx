import { AlertCircle, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { UI } from "@/lib/i18n/vi";

type EmptyStateProps = {
  title: string;
  description: string;
};

export const EmptyState = ({ title, description }: EmptyStateProps) => (
  <Card>
    <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <Inbox className="h-10 w-10 text-slate-600" aria-hidden />
      <div>
        <p className="font-medium text-slate-800">{title}</p>
        <p className="mt-1 max-w-md text-sm leading-relaxed text-slate-500">{description}</p>
      </div>
    </CardContent>
  </Card>
);

type ErrorStateProps = {
  message: string;
  section?: string;
  onRetry?: () => void;
};

export const ErrorState = ({ message, section, onRetry }: ErrorStateProps) => (
  <Card className="border-rose-200">
    <CardContent className="flex flex-col items-center justify-center gap-3 py-14 text-center">
      <AlertCircle className="h-10 w-10 text-rose-600" aria-hidden />
      <div>
        <p className="font-medium text-slate-800">
          {section ? UI.errorLoadSection(section) : UI.errorLoad}
        </p>
        <p className="mt-1 max-w-md text-sm text-slate-500">{message}</p>
      </div>
      {onRetry ? (
        <Button variant="outline" onClick={onRetry}>
          {UI.retry}
        </Button>
      ) : null}
    </CardContent>
  </Card>
);

export const QueryState = ({
  isLoading,
  isError,
  errorMessage,
  isEmpty,
  emptyTitle,
  emptyDescription,
  onRetry,
  loadingFallback,
  section,
  children,
}: {
  isLoading: boolean;
  isError: boolean;
  errorMessage?: string;
  isEmpty?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  onRetry?: () => void;
  loadingFallback?: React.ReactNode;
  section?: string;
  children: React.ReactNode;
}) => {
  if (isLoading) return loadingFallback ?? null;
  if (isError) {
    return (
      <ErrorState
        section={section}
        message={errorMessage ?? UI.errorGeneric}
        onRetry={onRetry}
      />
    );
  }
  if (isEmpty) {
    return (
      <EmptyState
        title={emptyTitle ?? UI.noData}
        description={emptyDescription ?? UI.noDataDescription}
      />
    );
  }
  return children;
};
