/**
 * Polled health map with a client-side "history buffer" per tool for
 * sparkline rendering. The backend returns a snapshot of current health;
 * we retain the last N samples in memory so the detail drawer can show
 * a latency trend without the backend having to expose a time-series.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { fetchHealth, reprobeHealth } from '@/lib/api';
import type { HealthMap } from '@/types/tool';

const MAX_SAMPLES = 60; // 60 * 15s ≈ 15 minutes
type Sample = { t: number; latency: number | null; status: string };

const historyBuffer: Map<string, Sample[]> = new Map();

function pushSamples(map: HealthMap): void {
  const now = Date.now();
  for (const [id, entry] of Object.entries(map)) {
    const arr = historyBuffer.get(id) ?? [];
    arr.push({ t: now, latency: entry.latency_ms ?? null, status: entry.status });
    while (arr.length > MAX_SAMPLES) arr.shift();
    historyBuffer.set(id, arr);
  }
}

export function getHealthHistory(toolId: string): Sample[] {
  return historyBuffer.get(toolId) ?? [];
}

export function useHealth(): {
  data: HealthMap | undefined;
  isLoading: boolean;
  isError: boolean;
  refetch: () => void;
  reprobe: (id: string) => void;
} {
  const qc = useQueryClient();
  const pushedRef = useRef<HealthMap | undefined>(undefined);

  const query = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    staleTime: 10_000,
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
  });

  useEffect(() => {
    if (query.data && query.data !== pushedRef.current) {
      pushSamples(query.data);
      pushedRef.current = query.data;
    }
  }, [query.data]);

  const reprobeMutation = useMutation({
    mutationFn: (id: string) => reprobeHealth(id),
    onSuccess: (delta) => {
      qc.setQueryData<HealthMap>(['health'], (prev) => ({
        ...(prev ?? {}),
        ...delta,
      }));
      pushSamples(delta);
    },
  });

  return {
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: () => void query.refetch(),
    reprobe: (id: string) => reprobeMutation.mutate(id),
  };
}
