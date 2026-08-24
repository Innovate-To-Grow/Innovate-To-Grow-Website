import {beforeEach, describe, expect, it, vi} from 'vitest'

import {renderError, renderSnapshot} from './render'
import {makeIncident, makeSnapshot} from './test/fixture'

describe('status page rendering', () => {
  let root: HTMLElement

  beforeEach(() => {
    document.body.replaceChildren()
    root = document.createElement('main')
    document.body.append(root)
  })

  it('renders the summary, fixed service groups, 90-day histories, and incidents', () => {
    const snapshot = makeSnapshot({incidents: [makeIncident()]})
    renderSnapshot(root, snapshot, 'live', vi.fn())

    expect(root.textContent).toContain('All systems operational')
    expect(root.textContent).toContain('Past 24 hours')
    expect(root.querySelectorAll('.component-card')).toHaveLength(5)
    expect(root.querySelectorAll('.history-bar')).toHaveLength(450)
    expect(root.querySelectorAll('tbody tr')).toHaveLength(450)
    expect(root.textContent).toContain('Production')
    expect(root.textContent).toContain('Demo')
    expect(root.textContent).toContain('Archive')
    expect(root.textContent).toContain('Intermittent production API errors')
    expect(root.querySelector('.history-bar')?.getAttribute('aria-label')).toContain('uptime')
    expect(root.getAttribute('aria-busy')).toBe('false')
  })

  it('marks stale and cached data as last known instead of current green status', () => {
    renderSnapshot(root, makeSnapshot({incidents: [makeIncident()]}), 'cache', vi.fn())
    expect(root.textContent).toContain('Status data is delayed')
    expect(root.textContent).toContain('Last known status')
    expect(root.textContent).toContain('Last known 24-hour summary')
    expect(root.textContent).toContain('Last known active incidents')
    expect(root.textContent).toContain('Last known health and 90-day uptime')
    expect(root.querySelector('.summary-section')?.getAttribute('data-source')).toBe('cache')
    expect(root.querySelector('.overall-panel')?.getAttribute('data-status')).toBe('unknown')
    for (const badge of root.querySelectorAll('.component-header .status-badge')) {
      expect(badge.textContent).toContain('Last known:')
      expect(badge.getAttribute('data-status')).toBe('unknown')
    }
    const incidentBadge = root.querySelector('.active-incidents-section .status-badge')
    expect(incidentBadge?.textContent).toContain('Last known:')
    expect(incidentBadge?.getAttribute('data-status')).toBe('unknown')
  })

  it.each([
    ['operational', 'All systems operational'],
    ['degraded', 'Some systems are degraded'],
    ['partial_outage', 'Some systems are unavailable'],
    ['major_outage', 'Major service outage'],
    ['maintenance', 'Maintenance in progress'],
    ['unknown', 'Current status is unavailable'],
  ] as const)('renders the %s overall state', (overallStatus, heading) => {
    renderSnapshot(root, makeSnapshot({status: overallStatus}), 'live', vi.fn())

    expect(root.textContent).toContain(heading)
    expect(root.querySelector('.overall-panel')?.getAttribute('data-status')).toBe(overallStatus)
  })

  it('orders active incidents before resolved incidents and newest first', () => {
    const oldestActive = makeIncident({
      id: 'oldest-active',
      state: 'investigating',
      startedAt: '2026-08-20T08:00:00Z',
      resolvedAt: null,
      title: 'Oldest active',
      updates: [{timestamp: '2026-08-20T08:00:00Z', state: 'investigating', message: 'Investigating.'}],
    })
    const newestActive = makeIncident({
      id: 'newest-active',
      state: 'monitoring',
      startedAt: '2026-08-20T10:00:00Z',
      resolvedAt: null,
      title: 'Newest active',
      updates: [
        {timestamp: '2026-08-20T10:00:00Z', state: 'investigating', message: 'Investigating.'},
        {timestamp: '2026-08-20T10:05:00Z', state: 'monitoring', message: 'Monitoring.'},
      ],
    })
    const resolved = makeIncident({
      title: 'Resolved incident',
      state: 'resolved',
      resolvedAt: '2026-08-20T11:25:00Z',
      updates: [
        {timestamp: '2026-08-20T11:10:00Z', state: 'investigating', message: 'Investigating.'},
        {timestamp: '2026-08-20T11:20:00Z', state: 'monitoring', message: 'Monitoring.'},
        {timestamp: '2026-08-20T11:25:00Z', state: 'resolved', message: 'Resolved.'},
      ],
    })
    renderSnapshot(root, makeSnapshot({incidents: [resolved, oldestActive, newestActive]}), 'live', vi.fn())

    const titles = [...root.querySelectorAll('.incident-card h3, .incident-card h4')].map(
      (node) => node.textContent,
    )
    expect(titles).toEqual(['Newest active', 'Oldest active', 'Resolved incident'])
    expect(root.querySelectorAll('.active-incidents-section .incident-card h3')).toHaveLength(2)
    expect(root.querySelectorAll('.incidents-section .incident-card h4')).toHaveLength(1)
    expect(root.querySelector('#active-incidents-heading')?.textContent).toBe('Active incidents')
    expect(root.querySelector('.incident-date')?.textContent).toBe('Aug 20, 2026')
  })

  it('uses one keyboard tab stop per component and arrow keys navigate each 90-day history', () => {
    renderSnapshot(root, makeSnapshot(), 'live', vi.fn())

    const cards = [...root.querySelectorAll<HTMLElement>('.component-card')]
    expect(root.querySelectorAll('.history-bar[tabindex="0"]')).toHaveLength(5)
    expect(root.querySelectorAll('.history-bar[tabindex="-1"]')).toHaveLength(445)

    const bars = [...cards[0]!.querySelectorAll<HTMLElement>('.history-bar')]
    expect(bars[89]!.getAttribute('aria-describedby')).toBe('history-help-production-website')
    expect(bars[89]!.getAttribute('aria-keyshortcuts')).toBe('ArrowLeft ArrowRight Home End')
    bars[89]!.focus()
    bars[89]!.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowLeft', bubbles: true}))
    expect(document.activeElement).toBe(bars[88])
    expect(bars[88]!.tabIndex).toBe(0)
    expect(bars[89]!.tabIndex).toBe(-1)

    bars[88]!.dispatchEvent(new KeyboardEvent('keydown', {key: 'Home', bubbles: true}))
    expect(document.activeElement).toBe(bars[0])
    bars[0]!.dispatchEvent(new KeyboardEvent('keydown', {key: 'End', bubbles: true}))
    expect(document.activeElement).toBe(bars[89])
  })

  it('renders untrusted snapshot strings as text, never markup', () => {
    const attack = '<img src=x onerror=alert(1)>'
    const incident = makeIncident({
      title: attack,
      updates: [{timestamp: '2026-08-20T11:10:00Z', state: 'investigating', message: attack}],
    })
    const snapshot = makeSnapshot({incidents: [incident]})
    snapshot.summary.message = attack
    snapshot.components[0]!.name = attack
    renderSnapshot(root, snapshot, 'live', vi.fn())
    expect(root.textContent?.match(/<img src=x onerror=alert\(1\)>/g)?.length).toBeGreaterThanOrEqual(4)
    expect(root.querySelector('img')).toBeNull()
    expect(root.querySelector('[onerror]')).toBeNull()
  })

  it('provides an honest retry state when no verified data is available', () => {
    const retry = vi.fn()
    renderError(root, retry)
    expect(root.getAttribute('aria-busy')).toBe('false')
    expect(root.textContent).toContain('does not necessarily mean the monitored services are down')
    const button = root.querySelector('button')
    button?.click()
    expect(retry).toHaveBeenCalledOnce()
  })
})
