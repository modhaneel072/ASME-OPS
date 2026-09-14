import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../client'
import { SEARCH_DEFAULT_LIMIT, SEARCH_MIN_LENGTH, SearchResponse } from '../contracts/search'

export const searchKeys = {
  all: ['search'] as const,
  query: (q: string, limit: number) => ['search', 'query', q, limit] as const,
}

export interface UseSearchOptions {
  limit?: number
  enabled?: boolean
}

/** `GET /search?q=&limit=`; disabled until the query is long enough. */
export function useSearch(q: string, { limit = SEARCH_DEFAULT_LIMIT, enabled = true }: UseSearchOptions = {}) {
  const text = q.trim()
  return useQuery({
    queryKey: searchKeys.query(text, limit),
    queryFn: async ({ signal }) => SearchResponse.parse(await api.get('/search', { params: { q: text, limit }, signal })),
    enabled: enabled && text.length >= SEARCH_MIN_LENGTH,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    retry: false,
  })
}
