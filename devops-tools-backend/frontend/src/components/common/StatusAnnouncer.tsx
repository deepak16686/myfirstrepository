/* Screen-reader-only aria-live region that announces tool status transitions. */
import { useEffect, useRef, useState } from 'react';
import type { HealthStatus, Tool } from '@/types/tool';

interface Props {
  tools: Tool[] | undefined;
}

export function StatusAnnouncer({ tools }: Props): React.ReactElement {
  const previousRef = useRef<Map<string, HealthStatus>>(new Map());
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!tools) return;
    const next: string[] = [];
    const prev = previousRef.current;
    for (const t of tools) {
      const status = (t.health_status ?? 'unknown') as HealthStatus;
      const was = prev.get(t.id);
      if (was !== undefined && was !== status) {
        next.push(`${t.name} is now ${status}`);
      }
      prev.set(t.id, status);
    }
    if (next.length > 0) {
      setMessage(next.join('. '));
    }
  }, [tools]);

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      className="sr-only"
      data-slot="status-announcer"
    >
      {message}
    </div>
  );
}
