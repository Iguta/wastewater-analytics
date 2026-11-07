import { useEffect, useState } from "react";

// Every screen has Loading, Error, Empty (section 10.1). A screen is never blank.
export function Loading({ onRetry }: { onRetry?: () => void }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => { const t = setTimeout(() => setSlow(true), 10_000); return () => clearTimeout(t); }, []);
  if (slow) return <ErrorState message="Can't reach the Dragonfly server (HTTP 504, no answer in 10 s)." onRetry={onRetry} />;
  return <div data-testid="state-loading" role="status" className="skeleton">Loading…</div>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div data-testid="state-error" role="alert" className="panel">
      <p>{message}</p>
      {onRetry && <button data-testid="retry-button" className="btn" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function EmptyState({ children, testId = "state-empty" }: { children: React.ReactNode; testId?: string }) {
  return <div data-testid={testId} className="panel">{children}</div>;
}
