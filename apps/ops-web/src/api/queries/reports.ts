import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../client'
import { OperationsReport, type OperationsReportParams } from '../contracts/reports'

export const reportKeys = {
  all: ['reports'] as const,
  operations: (params: OperationsReportParams) => ['reports', 'operations', params] as const,
}

/**
 * `GET /reports/operations`. Retry policy comes from the app QueryClient (no
 * retries on 4xx, so validation and unknown-filter errors surface at once).
 */
export function useOperationsReport(params: OperationsReportParams, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: reportKeys.operations(params),
    queryFn: async () =>
      OperationsReport.parse(
        await api.get('/reports/operations', {
          params: {
            range: params.range,
            start: params.range === 'custom' ? params.start : undefined,
            end: params.range === 'custom' ? params.end : undefined,
            'filter[project]': params.project,
            'filter[team]': params.team,
          },
        }),
      ),
    enabled: options.enabled ?? true,
    placeholderData: keepPreviousData,
  })
}
