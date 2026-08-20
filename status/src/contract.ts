export const STATUS_VALUES = [
  'operational',
  'degraded',
  'partial_outage',
  'major_outage',
  'maintenance',
  'unknown',
] as const

export const COMPONENT_IDS = [
  'production-website',
  'production-api',
  'demo-website',
  'demo-api',
  'project-archive',
] as const

export const GROUP_VALUES = ['production', 'demo', 'archive'] as const
export const INCIDENT_STATES = ['investigating', 'monitoring', 'resolved'] as const

export type StatusValue = (typeof STATUS_VALUES)[number]
export type ComponentId = (typeof COMPONENT_IDS)[number]
export type ComponentGroup = (typeof GROUP_VALUES)[number]
export type IncidentState = (typeof INCIDENT_STATES)[number]

export interface AvailabilitySummary {
  percent: number | null
  availableChecks: number
  eligibleChecks: number
  scheduledChecks: number
  maintenanceChecks: number
  monitoringCoveragePercent: number | null
}

export interface StatusSummary {
  message: string
  availability24h: AvailabilitySummary
  activeIncidentCount: number
  incidents24h: number
}

export interface HistoryDay {
  date: string
  status: StatusValue
  uptimePercent: number | null
  coveragePercent: number | null
  sampleCount: number
  maintenanceSampleCount: number
}

export interface StatusComponent {
  id: ComponentId
  name: string
  group: ComponentGroup
  status: StatusValue
  checkedAt: string
  uptime: {
    hours24: number | null
    days90: number | null
  }
  history: HistoryDay[]
}

export interface IncidentUpdate {
  timestamp: string
  state: IncidentState
  message: string
}

export interface StatusIncident {
  id: string
  kind: 'incident' | 'maintenance'
  state: IncidentState
  impact: StatusValue
  title: string
  startedAt: string
  resolvedAt: string | null
  affectedComponentIds: ComponentId[]
  updates: IncidentUpdate[]
}

export interface StatusSnapshotV1 {
  schemaVersion: 1
  generatedAt: string
  nextCheckAt: string
  stale: boolean
  overallStatus: StatusValue
  summary: StatusSummary
  components: StatusComponent[]
  incidents: StatusIncident[]
}

export type ValidationResult =
  | {ok: true; value: StatusSnapshotV1}
  | {ok: false; issues: string[]}

const DAY_MS = 86_400_000
const componentGroups: Record<ComponentId, ComponentGroup> = {
  'production-website': 'production',
  'production-api': 'production',
  'demo-website': 'demo',
  'demo-api': 'demo',
  'project-archive': 'archive',
}

class ContractError extends Error {}

function fail(path: string, message: string): never {
  throw new ContractError(`${path}: ${message}`)
}

function record(value: unknown, path: string, keys: readonly string[]): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    fail(path, 'must be an object')
  }
  const candidate = value as Record<string, unknown>
  const expected = new Set(keys)
  for (const key of keys) {
    if (!Object.hasOwn(candidate, key)) fail(path, `is missing ${key}`)
  }
  for (const key of Object.keys(candidate)) {
    if (!expected.has(key)) fail(path, `contains unexpected property ${key}`)
  }
  return candidate
}

function stringValue(value: unknown, path: string, maxLength: number, minLength = 0): string {
  if (typeof value !== 'string' || value.length < minLength || value.length > maxLength) {
    fail(path, `must be a string between ${minLength} and ${maxLength} characters`)
  }
  return value
}

function booleanValue(value: unknown, path: string): boolean {
  if (typeof value !== 'boolean') fail(path, 'must be a boolean')
  return value
}

function integerValue(value: unknown, path: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) {
    fail(path, 'must be a non-negative integer')
  }
  return value
}

function percentValue(value: unknown, path: string): number | null {
  if (value === null) return null
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 100) {
    fail(path, 'must be null or a number from 0 through 100')
  }
  const hundredths = value * 100
  if (Math.abs(hundredths - Math.round(hundredths)) > 1e-9) {
    fail(path, 'must use no more than two decimal places')
  }
  return value
}

function enumValue<const T extends readonly string[]>(value: unknown, path: string, options: T): T[number] {
  if (typeof value !== 'string' || !options.includes(value)) {
    fail(path, `must be one of ${options.join(', ')}`)
  }
  return value as T[number]
}

function dateTimeValue(value: unknown, path: string): string {
  const text = stringValue(value, path, 40, 1)
  const rfc3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/
  if (!rfc3339.test(text) || !Number.isFinite(Date.parse(text))) {
    fail(path, 'must be an RFC 3339 timestamp with a timezone')
  }
  return text
}

function dateValue(value: unknown, path: string): string {
  const text = stringValue(value, path, 10, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) fail(path, 'must be a YYYY-MM-DD date')
  const timestamp = Date.parse(`${text}T00:00:00Z`)
  if (!Number.isFinite(timestamp) || new Date(timestamp).toISOString().slice(0, 10) !== text) {
    fail(path, 'must be a real calendar date')
  }
  return text
}

function parseHistory(value: unknown, path: string): HistoryDay[] {
  if (!Array.isArray(value) || value.length !== 90) fail(path, 'must contain exactly 90 days')
  let previousTimestamp: number | null = null
  return value.map((entry, index) => {
    const itemPath = `${path}[${index}]`
    const item = record(entry, itemPath, [
      'date',
      'status',
      'uptimePercent',
      'coveragePercent',
      'sampleCount',
      'maintenanceSampleCount',
    ])
    const date = dateValue(item.date, `${itemPath}.date`)
    const timestamp = Date.parse(`${date}T00:00:00Z`)
    if (previousTimestamp !== null && timestamp - previousTimestamp !== DAY_MS) {
      fail(`${itemPath}.date`, 'must immediately follow the previous UTC date')
    }
    previousTimestamp = timestamp
    const sampleCount = integerValue(item.sampleCount, `${itemPath}.sampleCount`)
    const maintenanceSampleCount = integerValue(
      item.maintenanceSampleCount,
      `${itemPath}.maintenanceSampleCount`,
    )
    if (maintenanceSampleCount > sampleCount) {
      fail(`${itemPath}.maintenanceSampleCount`, 'cannot exceed sampleCount')
    }
    return {
      date,
      status: enumValue(item.status, `${itemPath}.status`, STATUS_VALUES),
      uptimePercent: percentValue(item.uptimePercent, `${itemPath}.uptimePercent`),
      coveragePercent: percentValue(item.coveragePercent, `${itemPath}.coveragePercent`),
      sampleCount,
      maintenanceSampleCount,
    }
  })
}

function parseComponent(value: unknown, path: string): StatusComponent {
  const item = record(value, path, ['id', 'name', 'group', 'status', 'checkedAt', 'uptime', 'history'])
  const id = enumValue(item.id, `${path}.id`, COMPONENT_IDS)
  const group = enumValue(item.group, `${path}.group`, GROUP_VALUES)
  if (componentGroups[id] !== group) fail(`${path}.group`, `does not match component ${id}`)
  const uptime = record(item.uptime, `${path}.uptime`, ['hours24', 'days90'])
  return {
    id,
    name: stringValue(item.name, `${path}.name`, 80, 1),
    group,
    status: enumValue(item.status, `${path}.status`, STATUS_VALUES),
    checkedAt: dateTimeValue(item.checkedAt, `${path}.checkedAt`),
    uptime: {
      hours24: percentValue(uptime.hours24, `${path}.uptime.hours24`),
      days90: percentValue(uptime.days90, `${path}.uptime.days90`),
    },
    history: parseHistory(item.history, `${path}.history`),
  }
}

function parseIncident(value: unknown, path: string): StatusIncident {
  const item = record(value, path, [
    'id',
    'kind',
    'state',
    'impact',
    'title',
    'startedAt',
    'resolvedAt',
    'affectedComponentIds',
    'updates',
  ])
  const state = enumValue(item.state, `${path}.state`, INCIDENT_STATES)
  const startedAt = dateTimeValue(item.startedAt, `${path}.startedAt`)
  let resolvedAt: string | null = null
  if (item.resolvedAt !== null) resolvedAt = dateTimeValue(item.resolvedAt, `${path}.resolvedAt`)
  if (state === 'resolved' && resolvedAt === null) fail(`${path}.resolvedAt`, 'is required for a resolved incident')
  if (state !== 'resolved' && resolvedAt !== null) fail(`${path}.resolvedAt`, 'must be null while an incident is active')
  if (resolvedAt !== null && Date.parse(resolvedAt) < Date.parse(startedAt)) {
    fail(`${path}.resolvedAt`, 'cannot be earlier than startedAt')
  }

  if (!Array.isArray(item.affectedComponentIds) || item.affectedComponentIds.length === 0) {
    fail(`${path}.affectedComponentIds`, 'must contain at least one component')
  }
  const affectedComponentIds = item.affectedComponentIds.map((id, index) =>
    enumValue(id, `${path}.affectedComponentIds[${index}]`, COMPONENT_IDS),
  )
  if (new Set(affectedComponentIds).size !== affectedComponentIds.length) {
    fail(`${path}.affectedComponentIds`, 'must not contain duplicates')
  }

  if (!Array.isArray(item.updates) || item.updates.length === 0) {
    fail(`${path}.updates`, 'must contain at least one update')
  }
  let previousUpdate = Date.parse(startedAt)
  const updates = item.updates.map((entry, index): IncidentUpdate => {
    const updatePath = `${path}.updates[${index}]`
    const update = record(entry, updatePath, ['timestamp', 'state', 'message'])
    const timestamp = dateTimeValue(update.timestamp, `${updatePath}.timestamp`)
    const parsedTimestamp = Date.parse(timestamp)
    if (parsedTimestamp < previousUpdate) fail(`${updatePath}.timestamp`, 'must be chronological')
    previousUpdate = parsedTimestamp
    return {
      timestamp,
      state: enumValue(update.state, `${updatePath}.state`, INCIDENT_STATES),
      message: stringValue(update.message, `${updatePath}.message`, 500, 1),
    }
  })
  if (updates.at(-1)?.state !== state) fail(`${path}.updates`, 'last update state must match incident state')

  return {
    id: stringValue(item.id, `${path}.id`, 100, 1),
    kind: enumValue(item.kind, `${path}.kind`, ['incident', 'maintenance'] as const),
    state,
    impact: enumValue(item.impact, `${path}.impact`, STATUS_VALUES),
    title: stringValue(item.title, `${path}.title`, 160, 1),
    startedAt,
    resolvedAt,
    affectedComponentIds,
    updates,
  }
}

function parseSummary(value: unknown): StatusSummary {
  const summary = record(value, '$.summary', [
    'message',
    'availability24h',
    'activeIncidentCount',
    'incidents24h',
  ])
  const availability = record(summary.availability24h, '$.summary.availability24h', [
    'percent',
    'availableChecks',
    'eligibleChecks',
    'scheduledChecks',
    'maintenanceChecks',
    'monitoringCoveragePercent',
  ])
  const availableChecks = integerValue(availability.availableChecks, '$.summary.availability24h.availableChecks')
  const eligibleChecks = integerValue(availability.eligibleChecks, '$.summary.availability24h.eligibleChecks')
  const scheduledChecks = integerValue(availability.scheduledChecks, '$.summary.availability24h.scheduledChecks')
  const maintenanceChecks = integerValue(
    availability.maintenanceChecks,
    '$.summary.availability24h.maintenanceChecks',
  )
  if (availableChecks > eligibleChecks) fail('$.summary.availability24h.availableChecks', 'cannot exceed eligibleChecks')
  if (eligibleChecks > scheduledChecks) fail('$.summary.availability24h.eligibleChecks', 'cannot exceed scheduledChecks')
  if (maintenanceChecks > scheduledChecks) {
    fail('$.summary.availability24h.maintenanceChecks', 'cannot exceed scheduledChecks')
  }
  return {
    message: stringValue(summary.message, '$.summary.message', 240),
    availability24h: {
      percent: percentValue(availability.percent, '$.summary.availability24h.percent'),
      availableChecks,
      eligibleChecks,
      scheduledChecks,
      maintenanceChecks,
      monitoringCoveragePercent: percentValue(
        availability.monitoringCoveragePercent,
        '$.summary.availability24h.monitoringCoveragePercent',
      ),
    },
    activeIncidentCount: integerValue(summary.activeIncidentCount, '$.summary.activeIncidentCount'),
    incidents24h: integerValue(summary.incidents24h, '$.summary.incidents24h'),
  }
}

export function validateStatusSnapshot(value: unknown): ValidationResult {
  try {
    const source = record(value, '$', [
      'schemaVersion',
      'generatedAt',
      'nextCheckAt',
      'stale',
      'overallStatus',
      'summary',
      'components',
      'incidents',
    ])
    if (source.schemaVersion !== 1) fail('$.schemaVersion', 'must equal 1')
    if (!Array.isArray(source.components) || source.components.length !== COMPONENT_IDS.length) {
      fail('$.components', 'must contain exactly five components')
    }
    const components = source.components.map((component, index) => parseComponent(component, `$.components[${index}]`))
    const componentIds = components.map(({id}) => id)
    if (new Set(componentIds).size !== COMPONENT_IDS.length || COMPONENT_IDS.some((id) => !componentIds.includes(id))) {
      fail('$.components', 'must contain each public component exactly once')
    }
    if (!Array.isArray(source.incidents)) fail('$.incidents', 'must be an array')
    const incidents = source.incidents.map((incident, index) => parseIncident(incident, `$.incidents[${index}]`))
    const snapshot: StatusSnapshotV1 = {
      schemaVersion: 1,
      generatedAt: dateTimeValue(source.generatedAt, '$.generatedAt'),
      nextCheckAt: dateTimeValue(source.nextCheckAt, '$.nextCheckAt'),
      stale: booleanValue(source.stale, '$.stale'),
      overallStatus: enumValue(source.overallStatus, '$.overallStatus', STATUS_VALUES),
      summary: parseSummary(source.summary),
      components,
      incidents,
    }
    return {ok: true, value: snapshot}
  } catch (error) {
    if (error instanceof ContractError) return {ok: false, issues: [error.message]}
    return {ok: false, issues: ['$: could not validate status data']}
  }
}

export function parseStatusSnapshot(value: unknown): StatusSnapshotV1 {
  const result = validateStatusSnapshot(value)
  if (!result.ok) throw new Error(`Invalid status response: ${result.issues.join('; ')}`)
  return result.value
}
