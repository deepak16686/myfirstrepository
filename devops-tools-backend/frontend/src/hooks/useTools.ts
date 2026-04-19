/**
 * TanStack Query hooks for the tool catalog + categories.
 */
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import {
  fetchCategories,
  fetchTool,
  fetchTools,
  fetchTailscaleStatus,
} from '@/lib/api';
import type { Category, TailscaleStatus, Tool } from '@/types/tool';

export function useTools(): UseQueryResult<Tool[], Error> {
  return useQuery({
    queryKey: ['tools'],
    queryFn: fetchTools,
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
}

export function useTool(id: string | undefined): UseQueryResult<Tool, Error> {
  return useQuery({
    queryKey: ['tool', id],
    queryFn: () => fetchTool(id as string),
    enabled: !!id,
    staleTime: 15_000,
  });
}

export function useCategories(): UseQueryResult<Category[], Error> {
  return useQuery({
    queryKey: ['categories'],
    queryFn: fetchCategories,
    staleTime: 5 * 60_000,
  });
}

export function useTailscale(): UseQueryResult<TailscaleStatus, Error> {
  return useQuery({
    queryKey: ['tailscale'],
    queryFn: fetchTailscaleStatus,
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  });
}
