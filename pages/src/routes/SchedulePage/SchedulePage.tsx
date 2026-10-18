import type {CSSProperties} from 'react';
import {useEffect, useMemo, useState} from 'react';
import {useSearchParams} from 'react-router';
import {ProjectGridTable, PROJECT_GRID_COLUMNS, createProjectGridItems, useProjectGridTable} from '@/features/projects';
import {useCurrentEventSchedule} from '@/features/events/hooks/useCurrentEventSchedule';
import {scheduleToneClass} from '@/features/events/scheduleTones';
import {scheduleProjectToGridRow} from '@/features/projects/api';
import {addMinutes} from '@/lib/format';

const SECTION_ORDER = ['CAP', 'CEE', 'ENGSL', 'CSE'] as const;
const GRAND_AWARD_LABELS: Record<string, string> = {
  CAP: 'F3 Innovate Engineering Award',
  CSE: 'F3 Innovate Software Award',
  CEE: 'F3 Innovate Civil & Environmental Award',
  ENGSL: 'F3 Innovate Engineering Award',
};

function buildTimeSlots(startTime: string, slotMinutes: number, maxOrder: number): string[] {
  const slots: string[] = [];
  let currentTime = startTime;

  for (let order = 1; order <= maxOrder; order += 1) {
    slots.push(currentTime);
    currentTime = addMinutes(currentTime, slotMinutes);
  }

  return slots;
}

function isFullyEmptyOrder(tracks: Array<{slots: Array<{order: number}>}>, order: number): boolean {
  return tracks.length > 0 && tracks.every((track) => !track.slots.some((slot) => slot.order === order));
}

interface SchedulePageProps {
  scheduleId?: string | null;
}

export const SchedulePage = ({scheduleId}: SchedulePageProps = {}) => {
  const [searchParams, setSearchParams] = useSearchParams();
  // An explicit prop (even null) wins: the embed page has already resolved the
  // block/widget/active precedence and validated the value. Only the standalone
  // /schedule route, which passes no prop, reads `?schedule_id=` itself.
  const selectedScheduleId = scheduleId === undefined ? searchParams.get('schedule_id') : scheduleId;
  const {data, loading, error} = useCurrentEventSchedule(selectedScheduleId);
  const teamSearch = searchParams.get('value') || '';
  const [isMobileLayout, setIsMobileLayout] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth <= 720 : false,
  );

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }

    const mediaQuery = window.matchMedia('(max-width: 720px)');
    const handleChange = (event: MediaQueryListEvent | MediaQueryList) => {
      setIsMobileLayout(event.matches);
    };

    handleChange(mediaQuery);
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  const orderedSections = useMemo(() => {
    if (!data) {
      return [];
    }

    const orderMap = new Map<string, number>(SECTION_ORDER.map((code, index) => [code, index]));

    return [...data.sections].sort((left, right) => {
      const leftRank = orderMap.get(left.code) ?? left.display_order + 100;
      const rightRank = orderMap.get(right.code) ?? right.display_order + 100;
      if (leftRank !== rightRank) {
        return leftRank - rightRank;
      }
      return left.display_order - right.display_order;
    });
  }, [data]);

  const winnerSections = useMemo(
    () =>
      orderedSections
        .map((section) => ({
          ...section,
          winnerTracks: section.tracks.filter((track) => track.winner),
        }))
        .filter((section) => section.winnerTracks.length > 0),
    [orderedSections],
  );

  const grandWinnerLines = useMemo(
    () =>
      (data?.grand_winners ?? []).map((grandWinner) => ({
        ...grandWinner,
        label: GRAND_AWARD_LABELS[grandWinner.section] ?? 'F3 Innovate Award',
      })),
    [data],
  );

  const schedulePageMeta = useMemo(() => {
    if (!data) return null;
    const parts = [data.event.date, data.event.location]
      .map((s) => (typeof s === 'string' ? s.trim() : ''))
      .filter((p) => p.length > 0);
    return parts.length > 0 ? parts.join(' · ') : null;
  }, [data]);

  const projectGridRows = useMemo(
    () => (data ? data.projects.filter((p) => p.is_presenting).map(scheduleProjectToGridRow) : []),
    [data],
  );
  const projectItems = useMemo(() => createProjectGridItems(projectGridRows, 'schedule-projects'), [projectGridRows]);
  const projectTable = useProjectGridTable({
    rows: projectItems,
    defaultSortField: 'class_code',
    defaultSortDirection: 'asc',
    initialSearch: teamSearch,
  });

  useEffect(() => {
    if (teamSearch && data) {
      document.getElementById('projects')?.scrollIntoView({behavior: 'smooth', block: 'start'});
    }
  }, [teamSearch, data]);

  const handleTeamClick = (searchValue: string) => {
    const nextParams = new URLSearchParams(searchParams);
    if (searchValue) {
      nextParams.set('value', searchValue);
    } else {
      nextParams.delete('value');
    }
    setSearchParams(nextParams, {replace: true});
    projectTable.setSearch(searchValue);
    document.getElementById('projects')?.scrollIntoView({behavior: 'smooth', block: 'start'});
  };

  if (loading) {
    return (
      <div className="schedule-page">
        <h1 className="itg-page-title schedule-page-title">Event Schedule</h1>
        <p className="schedule-page-state" role="status">Loading schedule...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="schedule-page">
        <h1 className="itg-page-title schedule-page-title">Event Schedule</h1>
        <p className="schedule-page-state schedule-page-state-error" role="alert">
          {error || 'Event schedule is unavailable.'}
        </p>
      </div>
    );
  }

  return (
    <div className="schedule-page">
      <header className="schedule-page-header" data-embed-section="schedule-header">
        <h1 className="itg-page-title schedule-page-title">{data.event.name}</h1>
        {schedulePageMeta ? <p className="itg-page-meta schedule-page-meta">{schedulePageMeta}</p> : null}
        {data.event.description ? <p className="itg-lead schedule-page-text">{data.event.description}</p> : null}
      </header>

      {data.show_winners && orderedSections.some((s) => s.tracks.some((t) => t.winner)) && (
        <section className="schedule-page-section schedule-page-section-winners" data-embed-section="schedule-winners">
          <div className="schedule-winners-hero">
            <h2 className="itg-section-title schedule-page-section-title schedule-winners-title">
              <span className="schedule-winners-title-emphasis">Winners!</span>{' '}
              <span className="schedule-winners-title-event">{data.event.name}</span>
            </h2>
            {grandWinnerLines.length > 0 && (
              <div className="schedule-grand-winners">
                {grandWinnerLines.map((grandWinner) => (
                  <p
                    className={`schedule-grand-winner-line is-${grandWinner.section.toLowerCase()}`}
                    key={`${grandWinner.section}-${grandWinner.winner}`}
                  >
                    <span className="schedule-grand-winner-label">{grandWinner.label}:</span> {grandWinner.winner}
                  </p>
                ))}
              </div>
            )}
          </div>
          <div className="schedule-winners">
            {winnerSections.map((section) => (
              <div className="schedule-winners-group" key={section.id}>
                <h3 className="schedule-class-label schedule-winners-group-title">
                  {section.label} ({section.code})
                </h3>
                <div
                  className="schedule-winners-grid"
                  style={
                    {
                      '--winner-column-count': section.winnerTracks.length,
                    } as CSSProperties
                  }
                >
                  {section.winnerTracks.map((track, index) => (
                    <article className={`schedule-winner-card ${scheduleToneClass(section.code, index)}`} key={track.id}>
                      <div className="schedule-winner-card-header">
                        <p className="schedule-winner-track">Track {track.track_number}</p>
                      </div>
                      <div className="schedule-winner-card-body">
                        <p className="schedule-winner-topic">{track.topic}</p>
                        <p className="schedule-winner-name">{track.winner}</p>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {data.expo.items.length > 0 && (
        <section className="schedule-page-section" data-embed-section="schedule-expo">
          <h2 className="itg-section-title schedule-page-section-title">{data.expo.title}</h2>
          <div className="schedule-page-agenda-wrap">
            <table className="schedule-page-agenda-table">
              <thead>
                <tr>
                  <th scope="col">Room:</th>
                  <th scope="col">{data.expo.location}</th>
                </tr>
              </thead>
              <tbody>
                {data.expo.items.map((item) => (
                  <tr key={item.id}>
                    <th scope="row">{item.time}</th>
                    <td>{item.title}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="schedule-page-section" data-embed-section="schedule-presentations">
        <h2 className="itg-section-title schedule-page-section-title">{data.presentations_title}</h2>
        <div className="schedule-page-section-stack">
          {orderedSections.map((section) => {
            const orderedTracks = [...section.tracks].sort(
              (left, right) => left.display_order - right.display_order || left.track_number - right.track_number,
            );
            const times = buildTimeSlots(section.start_time, section.slot_minutes, section.max_order);
            const fullyEmptyOrders = new Set(
              times
                .map((_, index) => index + 1)
                .filter((order) => isFullyEmptyOrder(orderedTracks, order)),
            );
            const showTopicRow = orderedTracks.some((track) => track.topic);

            return (
              <section key={section.id} className="schedule-presentation-block">
                <h3 className="schedule-class-label schedule-presentation-heading">
                  {section.label} ({section.code})
                </h3>

                {isMobileLayout ? (
                  <div className="schedule-page-mobile-grid">
                    {orderedTracks.map((track, columnIndex) => (
                      <article
                        key={`${section.id}-${track.id}-mobile`}
                        className={`schedule-mobile-card ${scheduleToneClass(section.code, columnIndex)}`}
                      >
                        <header className="schedule-mobile-card-header">
                          <div>
                            <p className="schedule-mobile-track-label">Track {track.track_number}</p>
                            <h4 className="schedule-mobile-topic">{track.topic || track.label || 'Presentation Track'}</h4>
                          </div>
                          <p className="schedule-mobile-room">{track.room || 'TBD'}</p>
                        </header>

                        <div className="schedule-mobile-slots">
                          {times.map((time, rowIndex) => {
                            const order = rowIndex + 1;
                            const slot = track.slots.find((entry) => entry.order === order);
                            const isFullyEmpty = fullyEmptyOrders.has(order);

                            return (
                              <div key={`${track.id}-${order}-mobile`} className="schedule-mobile-slot">
                                <div className="schedule-mobile-time">{time}</div>
                                <div className={`schedule-mobile-slot-content ${slot?.is_break || isFullyEmpty ? 'is-break' : ''}`}>
                                  {slot ? (
                                    slot.is_break ? (
                                      <span className="schedule-mobile-break">Break</span>
                                    ) : (
                                      <>
                                        <button
                                          type="button"
                                          className="schedule-mobile-team"
                                          onClick={() => handleTeamClick(slot.team_number || slot.display_text)}
                                        >
                                          {slot.display_text}
                                        </button>
                                        {slot.organization ? (
                                          <span className="schedule-mobile-org">{slot.organization}</span>
                                        ) : null}
                                      </>
                                    )
                                  ) : isFullyEmpty ? (
                                    <span className="schedule-mobile-break">Break</span>
                                  ) : null}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="schedule-page-table-wrap">
                    {/* The track count sizes the table's minimum width in the events sheet, so the grid
                        fits the main column and only scrolls when a class has too many tracks to fit. */}
                    <table
                      className={`schedule-presentation-table schedule-presentation-table--${section.code.toLowerCase()}`}
                      style={{'--schedule-track-count': orderedTracks.length} as CSSProperties}
                    >
                      {/* Narrow time column; the fixed layout shares the rest equally between tracks. */}
                      <colgroup>
                        <col className="schedule-presentation-time-col" />
                        {orderedTracks.map((track) => (
                          <col key={`${track.id}-col`} />
                        ))}
                      </colgroup>
                      <thead>
                        <tr>
                          <th className="schedule-presentation-corner">Room:</th>
                          {orderedTracks.map((track) => (
                            <th key={track.id} className="schedule-presentation-room">
                              {track.room || 'TBD'}
                            </th>
                          ))}
                        </tr>
                        <tr>
                          <th className="schedule-presentation-corner" />
                          {orderedTracks.map((track) => (
                            <th key={`${track.id}-label`} className="schedule-presentation-track">
                              Track {track.track_number}
                            </th>
                          ))}
                        </tr>
                        {showTopicRow && (
                          <tr>
                            <th className="schedule-presentation-corner" />
                            {orderedTracks.map((track, index) => (
                              <td
                                key={`${track.id}-topic`}
                                className={`schedule-presentation-topic-cell ${scheduleToneClass(section.code, index)}`}
                              >
                                <span className="schedule-presentation-topic">{track.topic || 'TBD'}</span>
                              </td>
                            ))}
                          </tr>
                        )}
                      </thead>
                      <tbody>
                        {times.map((time, rowIndex) => {
                          const order = rowIndex + 1;
                          const isFullyEmpty = fullyEmptyOrders.has(order);

                          return (
                            <tr key={`${section.id}-${order}`}>
                              <th scope="row" className="schedule-presentation-time">{time}</th>
                              {orderedTracks.map((track, columnIndex) => {
                                const slot = track.slots.find((entry) => entry.order === order);

                                return (
                                  <td
                                    key={`${track.id}-${order}`}
                                    className={`schedule-presentation-slot ${scheduleToneClass(section.code, columnIndex)}${
                                      slot?.is_break || isFullyEmpty ? ' schedule-presentation-slot-break' : ''
                                    }`}
                                    title={slot?.tooltip || ''}
                                  >
                                    {slot ? (
                                      slot.is_break ? (
                                        <span className="schedule-presentation-break">Break</span>
                                      ) : (
                                        <>
                                          <button
                                            type="button"
                                            className="schedule-presentation-team"
                                            onClick={() => handleTeamClick(slot.team_number || slot.display_text)}
                                          >
                                            {slot.display_text}
                                          </button>
                                          {slot.organization ? (
                                            <span className="schedule-presentation-org">{slot.organization}</span>
                                          ) : null}
                                        </>
                                      )
                                    ) : isFullyEmpty ? (
                                      <span className="schedule-presentation-break">Break</span>
                                    ) : null}
                                  </td>
                                );
                              })}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            );
          })}
        </div>
      </section>

      {data.awards.items.length > 0 && (
        <section className="schedule-page-section" data-embed-section="schedule-awards">
          <h2 className="itg-section-title schedule-page-section-title">{data.awards.title}</h2>
          <div className="schedule-page-agenda-wrap">
            <table className="schedule-page-agenda-table">
              <thead>
                <tr>
                  <th scope="col">Room:</th>
                  <th scope="col">{data.awards.location}</th>
                </tr>
              </thead>
              <tbody>
                {data.awards.items.map((item) => (
                  <tr key={item.id}>
                    <th scope="row">{item.time}</th>
                    <td>{item.title}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section id="projects" className="schedule-page-section" data-embed-section="schedule-projects">
        <h2 className="itg-section-title schedule-page-section-title">Projects &amp; Teams</h2>
        <p className="schedule-page-section-text">
          Click a team number above or search by title, organization, class, or track below.
        </p>
        <ProjectGridTable
          columns={PROJECT_GRID_COLUMNS}
          noResultsHeadingLevel={3}
          rows={projectItems}
          pagedRows={projectTable.pagedRows}
          filteredCount={projectTable.filteredRows.length}
          totalCount={projectItems.length}
          search={projectTable.search}
          sortField={projectTable.sortField}
          sortDirection={projectTable.sortDirection}
          onSearchChange={projectTable.setSearch}
          onSortChange={projectTable.toggleSort}
          expandedKeys={projectTable.expandedKeys}
          onToggleExpanded={projectTable.toggleExpanded}
          onToggleAllDetails={projectTable.toggleAllDetails}
          allDetailsExpanded={projectTable.allDetailsExpanded}
          page={projectTable.page}
          totalPages={projectTable.totalPages}
          onPageChange={projectTable.setPage}
          pageSize={projectTable.pageSize}
          pageSizeOptions={projectTable.pageSizeOptions}
          onPageSizeChange={projectTable.setPageSize}
          loading={false}
          error={null}
          emptyMessage="No projects available."
          countLabel="projects"
        />
      </section>
    </div>
  );
};
