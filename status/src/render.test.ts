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
    renderSnapshot(root, makeSnapshot(), 'cache', vi.fn())
    expect(root.textContent).toContain('Status data is delayed')
    expect(root.textContent).toContain('Last known status')
    expect(root.querySelector('.overall-panel')?.getAttribute('data-status')).toBe('unknown')
    for (const badge of root.querySelectorAll('.component-header .status-badge')) {
      expect(badge.textContent).toContain('Last known:')
      expect(badge.getAttribute('data-status')).toBe('unknown')
    }
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

    const titles = [...root.querySelectorAll('.incident-card h3')].map((node) => node.textContent)
    expect(titles).toEqual(['Newest active', 'Oldest active', 'Resolved incident'])
  })

  it('renders untrusted incident strings as text, never markup', () => {
    const incident = makeIncident({title: '<img src=x onerror=alert(1)>'})
    renderSnapshot(root, makeSnapshot({incidents: [incident]}), 'live', vi.fn())
    expect(root.textContent).toContain('<img src=x onerror=alert(1)>')
    expect(root.querySelector('img')).toBeNull()
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
