import type {CSSProperties} from 'react';
import {useEffect, useMemo, useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {ProjectGridTable, CURRENT_PROJECT_GRID_COLUMNS, createProjectGridItems, useProjectGridTable} from '../../components/Projects';
import {useCurrentEventSchedule} from '../../features/events/useCurrentEventSchedule';
import type {ProjectGridRow} from '../../features/projects/api';
import './SchedulePage.css';

const SECTION_ORDER = ['CAP', 'CEE', 'ENGSL', 'CSE'] as const;

const SECTION_THEMES: Record<
  string,
  {
    palette: string[];
    cellTextColor: string;
    organizationColor: string;
    topicTextColor: string;
  }
> = {
  CAP: {
    palette: ['#e7ba2d', '#e8c24f', '#ebca69', '#edd484', '#efdc9a'],
    cellTextColor: '#0f2d52',
    organizationColor: '#0f2d52',
    topicTextColor: '#0f2d52',
  },
  CEE: {
    palette: ['#c3dedd', '#b5d4d2', '#a8c8c6', '#9bbcbc', '#8fb0b0'],
    cellTextColor: '#0f2d52',
    organizationColor: '#0f2d52',
    topicTextColor: '#0f2d52',
  },
  ENGSL: {
    palette: ['#c3dedd', '#b5d4d2', '#a8c8c6', '#9bbcbc', '#8fb0b0'],
    cellTextColor: '#0f2d52',
    organizationColor: '#0f2d52',
    topicTextColor: '#0f2d52',
  },
  CSE: {
    palette: ['#25315f', '#33406f', '#414e7c', '#4b5888', '#556291'],
    cellTextColor: '#f0cb58',
    organizationColor: '#f0cb58',
    topicTextColor: '#f0cb58',
  },
};

function addMinutes(time: string, minutes: number): string {
  let [hours, mins] = time.split(':').map(Number);
  mins += minutes;

  while (mins >= 60) {
    hours += 1;
    mins -= 60;
  }

  if (hours > 12) {
    hours -= 12;
  }

  return `${hours}:${mins < 10 ? `0${mins}` : mins}`;
}

function toGridRow(row: {
  year_semester: string;
  class_code: string;
  team_number: string;
  team_name: string;
  project_title: string;
  organization: string;
  industry: string;
  abstract: string;
  student_names: string;
}): ProjectGridRow {
  return {
    semester_label: row.year_semester,
    class_code: row.class_code,
    team_number: row.team_number,
    team_name: row.team_name,
    project_title: row.project_title,
    organization: row.organization,
    industry: row.industry,
    abstract: row.abstract,
    student_names: row.student_names,
  };
}

function buildTimeSlots(startTime: string, slotMinutes: number, maxOrder: number): string[] {
  const slots: string[] = [];
  let currentTime = startTime;

  for (let order = 1; order <= maxOrder; order += 1) {
    slots.push(currentTime);
    currentTime = addMinutes(currentTime, slotMinutes);
  }

  return slots;
}

function columnStyle(sectionCode: string, columnIndex: number): CSSProperties {
  const theme = SECTION_THEMES[sectionCode] ?? SECTION_THEMES.CAP;
  const columnTone = theme.palette[Math.min(columnIndex, theme.palette.length - 1)];

  return {
    '--schedule-column-bg': columnTone,
    '--schedule-cell-text': theme.cellTextColor,
    '--schedule-org-color': theme.organizationColor,
    '--schedule-topic-color': theme.topicTextColor,
  } as CSSProperties;
}

export const SchedulePage = () => {
  const {data, loading, error} = useCurrentEventSchedule();
  const [searchParams, setSearchParams] = useSearchParams();
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

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    }

    mediaQuery.addListener(handleChange);
    return () => mediaQuery.removeListener(handleChange);
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

  const projectGridRows = useMemo(() => (data ? data.projects.map(toGridRow) : []), [data]);
  const projectItems = useMemo(() => createProjectGridItems(projectGridRows, 'schedule-projects'), [projectGridRows]);
  const projectTable = useProjectGridTable({
    rows: projectItems,
    pageSize: 10,
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
        <h1 className="schedule-page-title">Event Schedule</h1>
        <div className="schedule-page-state">Loading schedule...</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="schedule-page">
        <h1 className="schedule-page-title">Event Schedule</h1>
        <div className="schedule-page-state schedule-page-state-error">
          {error || 'Event schedule is unavailable.'}
        </div>
      </div>
    );
  }

  return (
    <div className="schedule-page">
      <header className="schedule-page-header">
        <h1 className="schedule-page-title">{data.event.name}</h1>
        <p className="schedule-page-meta">
          {data.event.date} · {data.event.location}
        </p>
        <p className="schedule-page-text">{data.event.description}</p>
      </header>

      {data.show_winners && orderedSections.some((s) => s.tracks.some((t) => t.winner)) && (
        <section className="schedule-page-section">
          <h2 className="schedule-page-section-title">Winners</h2>
          <div className="schedule-winners-wrap">
            <table className="schedule-winners-table">
              <thead>
                <tr>
                  <th>Section</th>
                  <th>Track</th>
                  <th>Topic</th>
                  <th>Winner</th>
                </tr>
              </thead>
              <tbody>
                {orderedSections.flatMap((section) =>
                  section.tracks
                    .filter((t) => t.winner)
                    .map((track) => (
                      <tr key={track.id}>
                        <td>{section.label}</td>
                        <td>Track {track.track_number}</td>
                        <td>{track.topic}</td>
                        <td className="schedule-winners-name">{track.winner}</td>
                      </tr>
                    )),
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {data.expo.items.length > 0 && (
        <section className="schedule-page-section">
          <h2 className="schedule-page-section-title">{data.expo.title}</h2>
          <div className="schedule-page-agenda-wrap">
            <table className="schedule-page-agenda-table">
              <thead>
                <tr>
                  <th>Room:</th>
                  <th>{data.expo.location}</th>
                </tr>
              </thead>
              <tbody>
                {data.expo.items.map((item) => (
                  <tr key={item.id}>
                    <th>{item.time}</th>
                    <td>{item.title}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="schedule-page-section">
        <h2 className="schedule-page-section-title schedule-page-section-title-main">{data.presentations_title}</h2>
        <div className="schedule-page-section-stack">
          {orderedSections.map((section) => {
            const orderedTracks = [...section.tracks].sort(
              (left, right) => left.display_order - right.display_order || left.track_number - right.track_number,
            );
            const times = buildTimeSlots(section.start_time, section.slot_minutes, section.max_order);
            const showTopicRow = orderedTracks.some((track) => track.topic);
            const columnWidth = `${100 / (orderedTracks.length + 1)}%`;

            return (
              <section key={section.id} className="schedule-presentation-block">
                <h3 className="schedule-presentation-heading">
                  {section.label} ({section.code})
                </h3>

                {isMobileLayout ? (
                  <div className="schedule-page-mobile-grid">
                    {orderedTracks.map((track, columnIndex) => (
                      <article
                        key={`${section.id}-${track.id}-mobile`}
                        className="schedule-mobile-card"
                        style={columnStyle(section.code, columnIndex)}
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

                            return (
                              <div key={`${track.id}-${order}-mobile`} className="schedule-mobile-slot">
                                <div className="schedule-mobile-time">{time}</div>
                                <div className={`schedule-mobile-slot-content ${slot?.is_break ? 'is-break' : ''}`}>
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
                                  ) : (
                                    <span className="schedule-mobile-empty">TBD</span>
                                  )}
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
                    <table className={`schedule-presentation-table schedule-presentation-table--${section.code.toLowerCase()}`}>
                      <colgroup>
                        <col style={{width: columnWidth}} />
                        {orderedTracks.map((track) => (
                          <col key={`${track.id}-col`} style={{width: columnWidth}} />
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
                                className="schedule-presentation-topic-cell"
                                style={columnStyle(section.code, index)}
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

                          return (
                            <tr key={`${section.id}-${order}`}>
                              <th className="schedule-presentation-time">{time}</th>
                              {orderedTracks.map((track, columnIndex) => {
                                const slot = track.slots.find((entry) => entry.order === order);

                                return (
                                  <td
                                    key={`${track.id}-${order}`}
                                    className={`schedule-presentation-slot ${slot?.is_break ? 'schedule-presentation-slot-break' : ''}`}
                                    style={columnStyle(section.code, columnIndex)}
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
                                    ) : (
                                      <span className="schedule-presentation-empty">TBD</span>
                                    )}
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
        <section className="schedule-page-section">
          <h2 className="schedule-page-section-title">{data.awards.title}</h2>
          <div className="schedule-page-agenda-wrap">
            <table className="schedule-page-agenda-table">
              <thead>
                <tr>
                  <th>Room:</th>
                  <th>{data.awards.location}</th>
                </tr>
              </thead>
              <tbody>
                {data.awards.items.map((item) => (
                  <tr key={item.id}>
                    <th>{item.time}</th>
                    <td>{item.title}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section id="projects" className="schedule-page-section">
        <h2 className="schedule-page-section-title">Projects &amp; Teams</h2>
        <p className="schedule-page-section-text">
          Click a team number above or search by title, organization, class, or track below.
        </p>
        <ProjectGridTable
          columns={CURRENT_PROJECT_GRID_COLUMNS}
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
          page={projectTable.page}
          totalPages={projectTable.totalPages}
          onPageChange={projectTable.setPage}
          loading={false}
          error={null}
          emptyMessage="No projects available."
          countLabel="projects"
        />
      </section>
    </div>
  );
};
