import type {
  ComponentGroup,
  HistoryDay,
  IncidentState,
  StatusComponent,
  StatusIncident,
  StatusSnapshotV1,
  StatusValue,
} from './contract'

export type SnapshotSource = 'live' | 'stale' | 'cache'

const statusLabels: Record<StatusValue, string> = {
  operational: 'Operational',
  degraded: 'Degraded performance',
  partial_outage: 'Partial outage',
  major_outage: 'Major outage',
  maintenance: 'Maintenance',
  unknown: 'No current data',
}

const overallHeadings: Record<StatusValue, string> = {
  operational: 'All systems operational',
  degraded: 'Some systems are degraded',
  partial_outage: 'Some systems are unavailable',
  major_outage: 'Major service outage',
  maintenance: 'Maintenance in progress',
  unknown: 'Current status is unavailable',
}

const groupLabels: Record<ComponentGroup, string> = {
  production: 'Production',
  demo: 'Demo',
  archive: 'Archive',
}

const stateLabels: Record<IncidentState, string> = {
  investigating: 'Investigating',
  monitoring: 'Monitoring',
  resolved: 'Resolved',
}

const pacificDateTime = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Los_Angeles',
  dateStyle: 'medium',
  timeStyle: 'short',
})

const historyDate = new Intl.DateTimeFormat('en-US', {
  timeZone: 'UTC',
  month: 'short',
  day: 'numeric',
  year: 'numeric',
})

const incidentDate = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Los_Angeles',
  month: 'short',
  day: 'numeric',
  year: 'numeric',
})

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const value = document.createElement(tag)
  if (className) value.className = className
  if (text !== undefined) value.textContent = text
  return value
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  return Number.isFinite(date.getTime()) ? pacificDateTime.format(date) : 'Unknown time'
}

function formatDate(date: string): string {
  const value = new Date(`${date}T12:00:00Z`)
  return Number.isFinite(value.getTime()) ? historyDate.format(value) : date
}

function formatPercent(percent: number | null): string {
  if (percent === null) return '—'
  return `${new Intl.NumberFormat('en-US', {maximumFractionDigits: 2}).format(percent)}%`
}

function statusBadge(status: StatusValue, override?: string): HTMLElement {
  const badge = element('span', 'status-badge', override ?? statusLabels[status])
  badge.dataset.status = override ? 'unknown' : status
  return badge
}

function formatIncidentDate(timestamp: string): string {
  const value = new Date(timestamp)
  return Number.isFinite(value.getTime()) ? incidentDate.format(value) : 'Unknown date'
}

function metric(label: string, value: string, detail: string): HTMLElement {
  const item = element('div', 'summary-stat')
  item.append(
    element('dt', 'metric-label', label),
    element('dd', 'metric-value', value),
    element('dd', 'metric-detail', detail),
  )
  return item
}

function renderOverview(snapshot: StatusSnapshotV1, source: SnapshotSource, onRefresh: () => void): HTMLElement {
  const isLastKnown = source !== 'live'
  const displayStatus: StatusValue = isLastKnown ? 'unknown' : snapshot.overallStatus
  const section = element('section', 'overall-panel')
  section.dataset.status = displayStatus
  section.setAttribute('aria-labelledby', 'overall-title')

  const copy = element('div', 'overall-copy')
  const eyebrow = element('p', 'eyebrow', isLastKnown ? 'Last verified update' : 'Current system status')
  const heading = element(
    'h1',
    undefined,
    isLastKnown ? 'Status data is delayed' : overallHeadings[snapshot.overallStatus],
  )
  heading.id = 'overall-title'
  const description = element(
    'p',
    'overall-description',
    isLastKnown
      ? `Live checks are unavailable. This page is showing the last verified data from ${formatTimestamp(snapshot.generatedAt)}.`
      : snapshot.summary.message,
  )
  const meta = element('p', 'last-checked')
  meta.append(
    element('span', 'status-dot'),
    document.createTextNode(
      isLastKnown
        ? ` Last known update: ${formatTimestamp(snapshot.generatedAt)}`
        : ` Last checked: ${formatTimestamp(snapshot.generatedAt)}`,
    ),
  )
  copy.append(eyebrow, heading, description, meta)

  const actions = element('div', 'overall-actions')
  actions.append(statusBadge(displayStatus, isLastKnown ? 'Last known status' : undefined))
  const refresh = element('button', 'refresh-button', 'Refresh status')
  refresh.type = 'button'
  refresh.dataset.refresh = 'true'
  refresh.addEventListener('click', onRefresh)
  actions.append(refresh)
  section.append(copy, actions)
  return section
}

function renderSummary(snapshot: StatusSnapshotV1, source: SnapshotSource): HTMLElement {
  const availability = snapshot.summary.availability24h
  const section = element('section', 'summary-section')
  section.dataset.source = source
  section.setAttribute('aria-labelledby', 'summary-heading')
  const intro = element('div', 'summary-heading-row')
  const heading = element(
    'h2',
    'section-title',
    source === 'live' ? 'Past 24 hours' : 'Last known 24-hour summary',
  )
  heading.id = 'summary-heading'
  intro.append(
    heading,
    element('p', 'section-kicker', 'Measured by independent five-minute checks'),
  )
  section.append(intro)
  const metrics = element('dl', 'summary-grid')
  metrics.append(
    metric(
      'Availability',
      formatPercent(availability.percent),
      `${availability.availableChecks} of ${availability.eligibleChecks} eligible checks`,
    ),
    metric(
      'Monitoring coverage',
      formatPercent(availability.monitoringCoveragePercent),
      `${availability.scheduledChecks} checks scheduled`,
    ),
    metric(
      'Maintenance checks',
      String(availability.maintenanceChecks),
      'Excluded from availability',
    ),
    metric(
      'Incidents',
      String(snapshot.summary.incidents24h),
      `${snapshot.summary.activeIncidentCount} currently active`,
    ),
  )
  section.append(metrics)
  return section
}

function historyDescription(day: HistoryDay): string {
  const uptime = day.uptimePercent === null ? 'no availability data' : `${formatPercent(day.uptimePercent)} uptime`
  const coverage = day.coveragePercent === null ? 'unknown coverage' : `${formatPercent(day.coveragePercent)} coverage`
  return `${formatDate(day.date)}: ${statusLabels[day.status]}, ${uptime}, ${coverage}`
}

function renderHistory(component: StatusComponent): HTMLElement {
  const container = element('div', 'history')
  const headingRow = element('div', 'history-heading')
  headingRow.append(
    element('span', undefined, 'Uptime over the past 90 days'),
    element('span', 'history-caption', 'Daily checks'),
  )
  container.append(headingRow)

  const keyboardHelp = element(
    'p',
    'visually-hidden',
    'Use Left and Right Arrow, Home, or End to review daily status checks.',
  )
  keyboardHelp.id = `history-help-${component.id}`
  container.append(keyboardHelp)

  const bars = element('ol', 'history-bars')
  bars.setAttribute('aria-label', `${component.name} daily status for the past 90 days`)
  const barElements: HTMLElement[] = []
  for (const [index, day] of component.history.entries()) {
    const listItem = element('li')
    const bar = element('span', 'history-bar')
    bar.dataset.status = day.status
    bar.tabIndex = index === component.history.length - 1 ? 0 : -1
    bar.setAttribute('role', 'img')
    bar.setAttribute('aria-label', historyDescription(day))
    bar.setAttribute('aria-describedby', keyboardHelp.id)
    bar.setAttribute('aria-keyshortcuts', 'ArrowLeft ArrowRight Home End')
    bar.title = historyDescription(day)
    barElements.push(bar)
    listItem.append(bar)
    bars.append(listItem)
  }
  for (const [index, bar] of barElements.entries()) {
    bar.addEventListener('focus', () => {
      for (const item of barElements) item.tabIndex = item === bar ? 0 : -1
    })
    bar.addEventListener('keydown', (event) => {
      let targetIndex: number | null = null
      if (event.key === 'ArrowLeft') targetIndex = Math.max(0, index - 1)
      if (event.key === 'ArrowRight') targetIndex = Math.min(barElements.length - 1, index + 1)
      if (event.key === 'Home') targetIndex = 0
      if (event.key === 'End') targetIndex = barElements.length - 1
      if (targetIndex === null) return
      event.preventDefault()
      if (targetIndex === index) return
      barElements[targetIndex]?.focus()
    })
  }
  container.append(bars)

  const axis = element('div', 'history-axis')
  axis.append(
    element('span', undefined, '90 days ago'),
    element('strong', undefined, `${formatPercent(component.uptime.days90)} uptime`),
    element('span', undefined, 'Today'),
  )
  container.append(axis)

  const details = element('details', 'history-details')
  details.append(element('summary', undefined, 'View accessible daily history table'))
  const tableWrap = element('div', 'table-wrap')
  const table = element('table')
  const caption = element('caption', 'visually-hidden', `${component.name} 90-day status history`)
  const header = element('thead')
  const headerRow = element('tr')
  for (const label of ['Date', 'Status', 'Uptime', 'Coverage', 'Samples', 'Maintenance']) {
    const cell = element('th', undefined, label)
    cell.scope = 'col'
    headerRow.append(cell)
  }
  header.append(headerRow)
  const body = element('tbody')
  for (const day of [...component.history].reverse()) {
    const row = element('tr')
    const dateCell = element('th', undefined, formatDate(day.date))
    dateCell.scope = 'row'
    row.append(
      dateCell,
      element('td', undefined, statusLabels[day.status]),
      element('td', undefined, formatPercent(day.uptimePercent)),
      element('td', undefined, formatPercent(day.coveragePercent)),
      element('td', undefined, String(day.sampleCount)),
      element('td', undefined, String(day.maintenanceSampleCount)),
    )
    body.append(row)
  }
  table.append(caption, header, body)
  tableWrap.append(table)
  details.append(tableWrap)
  container.append(details)
  return container
}

function renderLegend(): HTMLElement {
  const legend = element('ul', 'legend')
  legend.setAttribute('aria-label', 'Daily history legend')
  const entries: Array<[StatusValue, string]> = [
    ['operational', 'Operational'],
    ['degraded', 'Degraded'],
    ['partial_outage', 'Partial outage'],
    ['major_outage', 'Major outage'],
    ['maintenance', 'Maintenance'],
    ['unknown', 'No data'],
  ]
  for (const [status, label] of entries) {
    const item = element('li')
    const swatch = element('span', 'legend-swatch')
    swatch.dataset.status = status
    swatch.setAttribute('aria-hidden', 'true')
    item.append(swatch, document.createTextNode(label))
    legend.append(item)
  }
  return legend
}

function renderComponent(component: StatusComponent, source: SnapshotSource): HTMLElement {
  const article = element('article', 'component-card')
  article.dataset.status = source === 'live' ? component.status : 'unknown'
  const header = element('div', 'component-header')
  const titleBlock = element('div')
  const title = element('h4', undefined, component.name)
  titleBlock.append(title, element('p', 'component-checked', `Checked ${formatTimestamp(component.checkedAt)}`))
  const badge = statusBadge(
    component.status,
    source === 'live' ? undefined : `Last known: ${statusLabels[component.status]}`,
  )
  header.append(titleBlock, badge)
  const uptime = element('dl', 'uptime-list')
  for (const [term, value] of [
    ['Past 24 hours', component.uptime.hours24],
    ['Past 90 days', component.uptime.days90],
  ] as const) {
    const group = element('div')
    group.append(element('dt', undefined, term), element('dd', undefined, formatPercent(value)))
    uptime.append(group)
  }
  article.append(header, uptime, renderHistory(component))
  return article
}

function renderComponents(snapshot: StatusSnapshotV1, source: SnapshotSource): HTMLElement {
  const section = element('section', 'components-section')
  section.setAttribute('aria-labelledby', 'components-heading')
  const intro = element('div', 'section-heading-row')
  const titleWrap = element('div')
  const heading = element('h2', 'section-title', 'Services')
  heading.id = 'components-heading'
  titleWrap.append(
    heading,
    element(
      'p',
      'section-description',
      source === 'live'
        ? 'Current health and 90-day uptime for every monitored service.'
        : 'Last known health and 90-day uptime for every monitored service.',
    ),
  )
  intro.append(titleWrap, renderLegend())
  section.append(intro)
  for (const group of ['production', 'demo', 'archive'] as const) {
    const groupSection = element('section', 'service-group')
    const groupHeading = element('h3', 'group-title', groupLabels[group])
    const groupId = `group-${group}`
    groupHeading.id = groupId
    groupSection.setAttribute('aria-labelledby', groupId)
    const cards = element('div', 'component-list')
    for (const component of snapshot.components.filter((item) => item.group === group)) {
      cards.append(renderComponent(component, source))
    }
    groupSection.append(groupHeading, cards)
    section.append(groupSection)
  }
  return section
}

function incidentCard(
  incident: StatusIncident,
  components: StatusComponent[],
  headingLevel: 'h3' | 'h4',
  isLastKnown = false,
): HTMLElement {
  const article = element('article', 'incident-card')
  article.dataset.state = incident.state
  article.dataset.impact = incident.impact
  article.dataset.source = isLastKnown ? 'last-known' : 'live'
  const header = element('div', 'incident-header')
  const titleWrap = element('div')
  const incidentState = incident.kind === 'maintenance' ? 'Maintenance' : stateLabels[incident.state]
  const eyebrow = element(
    'p',
    'incident-eyebrow',
    isLastKnown ? `Last known · ${incidentState}` : incidentState,
  )
  titleWrap.append(eyebrow, element(headingLevel, undefined, incident.title))
  header.append(
    titleWrap,
    statusBadge(
      incident.impact,
      isLastKnown ? `Last known: ${statusLabels[incident.impact]}` : undefined,
    ),
  )
  const affectedNames = incident.affectedComponentIds.map(
    (id) => components.find((component) => component.id === id)?.name ?? id,
  )
  const meta = element(
    'p',
    'incident-meta',
    `${incident.state === 'resolved' ? 'Resolved' : 'Started'} ${formatTimestamp(
      incident.resolvedAt ?? incident.startedAt,
    )} · ${affectedNames.join(', ')}`,
  )
  const updates = element('ol', 'incident-updates')
  for (const update of [...incident.updates].reverse()) {
    const item = element('li')
    const updateHeader = element('p', 'update-heading')
    updateHeader.append(element('strong', undefined, stateLabels[update.state]), document.createTextNode(` · ${formatTimestamp(update.timestamp)}`))
    item.append(updateHeader, element('p', undefined, update.message))
    updates.append(item)
  }
  article.append(header, meta, updates)
  return article
}

function sortIncidents(incidents: StatusIncident[]): StatusIncident[] {
  return [...incidents].sort((left, right) => Date.parse(right.startedAt) - Date.parse(left.startedAt))
}

function renderActiveIncidents(snapshot: StatusSnapshotV1, source: SnapshotSource): HTMLElement | null {
  const active = sortIncidents(snapshot.incidents.filter(({state}) => state !== 'resolved'))
  if (active.length === 0) return null

  const section = element('section', 'active-incidents-section')
  section.dataset.source = source
  section.setAttribute('aria-labelledby', 'active-incidents-heading')
  const heading = element(
    'h2',
    'section-title',
    source === 'live' ? 'Active incidents' : 'Last known active incidents',
  )
  heading.id = 'active-incidents-heading'
  section.append(heading)
  const list = element('div', 'active-incident-list')
  for (const incident of active) {
    list.append(incidentCard(incident, snapshot.components, 'h3', source !== 'live'))
  }
  section.append(list)
  return section
}

function renderIncidentHistory(snapshot: StatusSnapshotV1): HTMLElement {
  const section = element('section', 'incidents-section')
  section.setAttribute('aria-labelledby', 'incidents-heading')
  const heading = element('h2', 'section-title', 'Past incidents')
  heading.id = 'incidents-heading'
  section.append(
    heading,
    element('p', 'section-description', 'Resolved incidents recorded during the past 90 days.'),
  )

  const resolved = sortIncidents(snapshot.incidents.filter(({state}) => state === 'resolved'))
  if (resolved.length === 0) {
    const empty = element('div', 'empty-incidents')
    empty.append(
      element('span', 'empty-check', '✓'),
      element('p', undefined, 'No incidents have been recorded in the past 90 days.'),
    )
    section.append(empty)
    return section
  }

  const groups = new Map<string, StatusIncident[]>()
  for (const incident of resolved) {
    const date = formatIncidentDate(incident.startedAt)
    groups.set(date, [...(groups.get(date) ?? []), incident])
  }
  const history = element('div', 'incident-history')
  for (const [date, incidents] of groups) {
    const day = element('section', 'incident-day')
    const dayHeading = element('h3', 'incident-date', date)
    day.append(dayHeading)
    const list = element('div', 'incident-list')
    for (const incident of incidents) list.append(incidentCard(incident, snapshot.components, 'h4'))
    day.append(list)
    history.append(day)
  }
  section.append(history)
  return section
}

export function renderSnapshot(
  root: HTMLElement,
  snapshot: StatusSnapshotV1,
  source: SnapshotSource,
  onRefresh: () => void,
): void {
  const sections = [renderOverview(snapshot, source, onRefresh)]
  const activeIncidents = renderActiveIncidents(snapshot, source)
  if (activeIncidents) sections.push(activeIncidents)
  sections.push(
    renderSummary(snapshot, source),
    renderComponents(snapshot, source),
    renderIncidentHistory(snapshot),
  )
  root.replaceChildren(...sections)
  root.setAttribute('aria-busy', 'false')
}

export function renderError(root: HTMLElement, onRetry: () => void): void {
  const panel = element('section', 'panel error-panel')
  panel.setAttribute('role', 'alert')
  panel.append(
    element('p', 'eyebrow', 'Status service unavailable'),
    element('h1', undefined, 'Current status could not be loaded'),
    element(
      'p',
      'error-description',
      'No verified update is available on this device. This does not necessarily mean the monitored services are down.',
    ),
  )
  const retry = element('button', 'refresh-button', 'Try again')
  retry.type = 'button'
  retry.dataset.refresh = 'true'
  retry.addEventListener('click', onRetry)
  panel.append(retry)
  root.replaceChildren(panel)
  root.setAttribute('aria-busy', 'false')
}
