import { useEffect, useState } from "react";

// Every screen has Loading, Error, Empty (section 10.1). A screen is never blank.
export function Loading() {
  const [slow, setSlow] = useState(false);
  useEffect(() => { const t = setTimeout(() => setSlow(true), 10_000); return () => clearTimeout(t); }, []);
  if (slow) return <ErrorState message="Can't reach the Dragonfly server (timed out after 10 s)." />;
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

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <div data-testid="state-empty" className="panel">{children}</div>;
}
