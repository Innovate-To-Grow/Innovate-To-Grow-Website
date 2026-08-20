import {
  COMPONENT_IDS,
  type ComponentGroup,
  type StatusIncident,
  type StatusSnapshotV1,
  type StatusValue,
} from '../contract'

const names = {
  'production-website': 'Production Website',
  'production-api': 'Production API',
  'demo-website': 'Demo Website',
  'demo-api': 'Demo API',
  'project-archive': 'Project Archive',
} as const

const groups: Record<(typeof COMPONENT_IDS)[number], ComponentGroup> = {
  'production-website': 'production',
  'production-api': 'production',
  'demo-website': 'demo',
  'demo-api': 'demo',
  'project-archive': 'archive',
}

export function makeIncident(overrides: Partial<StatusIncident> = {}): StatusIncident {
  return {
    id: 'incident-2026-08-20-production-api',
    kind: 'incident',
    state: 'monitoring',
    impact: 'degraded',
    title: 'Intermittent production API errors',
    startedAt: '2026-08-20T11:10:00Z',
    resolvedAt: null,
    affectedComponentIds: ['production-api'],
    updates: [
      {
        timestamp: '2026-08-20T11:10:00Z',
        state: 'investigating',
        message: 'Automated checks detected repeated API errors.',
      },
      {
        timestamp: '2026-08-20T11:20:00Z',
        state: 'monitoring',
        message: 'The API has recovered and automated checks are monitoring stability.',
      },
    ],
    ...overrides,
  }
}

export function makeSnapshot(options: {
  generatedAt?: string
  stale?: boolean
  status?: StatusValue
  incidents?: StatusIncident[]
} = {}): StatusSnapshotV1 {
  const generatedAt = options.generatedAt ?? '2026-08-20T12:00:00Z'
  const status = options.status ?? 'operational'
  const lastDate = Date.parse(`${generatedAt.slice(0, 10)}T00:00:00Z`)
  const history = Array.from({length: 90}, (_, index) => ({
    date: new Date(lastDate - (89 - index) * 86_400_000).toISOString().slice(0, 10),
    status,
    uptimePercent: status === 'unknown' ? null : 100,
    coveragePercent: status === 'unknown' ? null : 100,
    sampleCount: status === 'unknown' ? 0 : 288,
    maintenanceSampleCount: 0,
  }))
  const incidents = options.incidents ?? []
  return {
    schemaVersion: 1,
    generatedAt,
    nextCheckAt: new Date(Date.parse(generatedAt) + 5 * 60 * 1_000).toISOString(),
    stale: options.stale ?? false,
    overallStatus: status,
    summary: {
      message: status === 'operational' ? 'All monitored services are operating normally.' : 'Some services need attention.',
      availability24h: {
        percent: 100,
        availableChecks: 1_435,
        eligibleChecks: 1_435,
        scheduledChecks: 1_440,
        maintenanceChecks: 5,
        monitoringCoveragePercent: 100,
      },
      activeIncidentCount: incidents.filter(({state}) => state !== 'resolved').length,
      incidents24h: incidents.length,
    },
    components: COMPONENT_IDS.map((id) => ({
      id,
      name: names[id],
      group: groups[id],
      status,
      checkedAt: generatedAt,
      uptime: {hours24: status === 'unknown' ? null : 100, days90: status === 'unknown' ? null : 99.99},
      history: structuredClone(history),
    })),
    incidents,
  }
}

export class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>()

  get length(): number {
    return this.values.size
  }

  clear(): void {
    this.values.clear()
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null
  }

  key(index: number): string | null {
    return [...this.values.keys()][index] ?? null
  }

  removeItem(key: string): void {
    this.values.delete(key)
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value)
  }
}
