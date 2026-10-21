import {useEffect, useMemo} from 'react';
import {useSearchParams} from 'react-router';
import {
  ProjectGridTable,
  PROJECT_GRID_COLUMNS,
  createProjectGridItems,
  useProjectGridTable,
  type ProjectGridItem,
} from '@/features/projects';
import {useCurrentEventSchedule} from '@/features/events/hooks/useCurrentEventSchedule';
import {scheduleProjectToGridRow} from '@/features/projects/api';
import {AgendaSection} from './schedule/AgendaSection';
import {PresentationSection} from './schedule/PresentationSection';
import {orderSections} from './schedule/scheduleModel';
import {useMobileScheduleLayout} from './schedule/useMobileScheduleLayout';
import {WinnersSection} from './schedule/WinnersSection';

interface SchedulePageProps {
  scheduleId?: string | null;
}

const ScheduleMessage = ({children, isError = false}: {children: string; isError?: boolean}) => (
  <div className="schedule-page">
    <h1 className="itg-page-title schedule-page-title">Event Schedule</h1>
    <p
      className={`schedule-page-state${isError ? ' schedule-page-state-error' : ''}`}
      role={isError ? 'alert' : 'status'}
    >
      {children}
    </p>
  </div>
);

type ScheduleEvent = NonNullable<ReturnType<typeof useCurrentEventSchedule>['data']>['event'];

/** The event's date and location under the title. */
const ScheduleMeta = ({event}: {event: ScheduleEvent}) => {
  const parts = [event.date, event.location]
    .map((s) => (typeof s === 'string' ? s.trim() : ''))
    .filter((p) => p.length > 0);
  return parts.length > 0 ? <p className="itg-page-meta schedule-page-meta">{parts.join(' · ')}</p> : null;
};

interface ScheduleProjectsSectionProps {
  items: ProjectGridItem[];
  table: ReturnType<typeof useProjectGridTable>;
}

/** The searchable list of presenting projects; the team buttons above search it. */
const ScheduleProjectsSection = ({items, table}: ScheduleProjectsSectionProps) => (
  <section id="projects" className="schedule-page-section" data-embed-section="schedule-projects">
    <h2 className="itg-section-title schedule-page-section-title">Projects &amp; Teams</h2>
    <p className="schedule-page-section-text">
      Click a team number above or search by title, organization, class, or track below.
    </p>
    <ProjectGridTable
      columns={PROJECT_GRID_COLUMNS}
      noResultsHeadingLevel={3}
      rows={items}
      pagedRows={table.pagedRows}
      filteredCount={table.filteredRows.length}
      totalCount={items.length}
      search={table.search}
      sortField={table.sortField}
      sortDirection={table.sortDirection}
      onSearchChange={table.setSearch}
      onSortChange={table.toggleSort}
      expandedKeys={table.expandedKeys}
      onToggleExpanded={table.toggleExpanded}
      onToggleAllDetails={table.toggleAllDetails}
      allDetailsExpanded={table.allDetailsExpanded}
      page={table.page}
      totalPages={table.totalPages}
      onPageChange={table.setPage}
      pageSize={table.pageSize}
      pageSizeOptions={table.pageSizeOptions}
      onPageSizeChange={table.setPageSize}
      loading={false}
      error={null}
      emptyMessage="No projects available."
      countLabel="projects"
    />
  </section>
);

/**
 * The event schedule: winners, the expo agenda, each class's presentation grid, the awards agenda and
 * a searchable list of presenting projects. Clicking a team in the grid searches that list.
 */
export const SchedulePage = ({scheduleId}: SchedulePageProps = {}) => {
  const [searchParams, setSearchParams] = useSearchParams();
  // An explicit prop (even null) wins: the embed page has already resolved the
  // block/widget/active precedence and validated the value. Only the standalone
  // /schedule route, which passes no prop, reads `?schedule_id=` itself.
  const selectedScheduleId = scheduleId === undefined ? searchParams.get('schedule_id') : scheduleId;
  const {data, loading, error} = useCurrentEventSchedule(selectedScheduleId);
  const teamSearch = searchParams.get('value') || '';
  const isMobileLayout = useMobileScheduleLayout();

  const orderedSections = useMemo(() => (data ? orderSections(data.sections) : []), [data]);

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
    return <ScheduleMessage>Loading schedule...</ScheduleMessage>;
  }
  if (error || !data) {
    return <ScheduleMessage isError>{error || 'Event schedule is unavailable.'}</ScheduleMessage>;
  }

  return (
    <div className="schedule-page">
      <header className="schedule-page-header" data-embed-section="schedule-header">
        <h1 className="itg-page-title schedule-page-title">{data.event.name}</h1>
        <ScheduleMeta event={data.event} />
        {data.event.description ? <p className="itg-lead schedule-page-text">{data.event.description}</p> : null}
      </header>

      {data.show_winners && orderedSections.some((s) => s.tracks.some((t) => t.winner)) && (
        <WinnersSection data={data} sections={orderedSections} />
      )}

      <AgendaSection agenda={data.expo} embedSection="schedule-expo" />

      <section className="schedule-page-section" data-embed-section="schedule-presentations">
        <h2 className="itg-section-title schedule-page-section-title">{data.presentations_title}</h2>
        <div className="schedule-page-section-stack">
          {orderedSections.map((section) => (
            <PresentationSection
              key={section.id}
              section={section}
              isMobileLayout={isMobileLayout}
              onTeamClick={handleTeamClick}
            />
          ))}
        </div>
      </section>

      <AgendaSection agenda={data.awards} embedSection="schedule-awards" />

      <ScheduleProjectsSection items={projectItems} table={projectTable} />
    </div>
  );
};
