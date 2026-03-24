import {useCurrentProjectsData} from '../../hooks/useCurrentProjectsData';
import {ScheduleGrid} from '../../components/ScheduleGrid';
import {SheetsDataTable} from '../../components/SheetsDataTable';
import {SCHEDULE_CLASS_CONFIGS} from '../../config/scheduleConfig';
import './SchedulePage.css';

export const SchedulePage = () => {
  const {rows, loading, error} = useCurrentProjectsData();
  const trackInfos: {name: string; room: string; zoomLink: string}[] = [];

  return (
    <div className="schedule-page">
      <h1 className="schedule-page-title">Event Schedule</h1>

      <p className="schedule-page-text">
        View the presentation schedule for the current Innovate to Grow event. Each class has its
        own set of tracks with assigned rooms and time slots. Click on a team number in the grid
        to search for that team in the projects table below.
      </p>

      <section className="schedule-page-section">
        <ScheduleGrid
          classes={SCHEDULE_CLASS_CONFIGS}
          rows={rows}
          trackInfos={trackInfos}
          loading={loading}
          error={error}
        />
      </section>

      <section className="schedule-page-section">
        <h2 className="schedule-page-section-title">All Projects</h2>
        <SheetsDataTable rows={rows} loading={loading} error={error} />
      </section>
    </div>
  );
};
