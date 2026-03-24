import {useState, useCallback} from 'react';
import {useParams, Link} from 'react-router-dom';
import {usePastProjectsData} from '../../hooks/usePastProjectsData';
import {ScheduleGrid} from '../../components/ScheduleGrid';
import {SheetsDataTable} from '../../components/SheetsDataTable';
import {EVENT_CONFIGS} from './eventConfigs';
import './EventArchivePage.css';

export const EventArchivePage = () => {
  const {eventSlug} = useParams<{eventSlug: string}>();
  const config = eventSlug ? EVENT_CONFIGS[eventSlug] : undefined;

  const {rows, loading, error} = usePastProjectsData();
  const trackInfos: {name: string; room: string; zoomLink: string}[] = [];

  const [teamSearch, setTeamSearch] = useState('');

  const handleTeamClick = useCallback((teamNum: string) => {
    setTeamSearch(teamNum);
    document.getElementById('projects')?.scrollIntoView({behavior: 'smooth'});
  }, []);

  if (!config) {
    return (
      <div className="ea-page">
        <h1 className="ea-title">Event Not Found</h1>
        <p className="ea-text">
          The event archive &quot;{eventSlug}&quot; does not exist.
        </p>
        <Link to="/past-events" className="ea-back-link">
          View all past events
        </Link>
      </div>
    );
  }

  const hasSchedule = config.classes.length > 0;

  return (
    <div className="ea-page">
      <div className="ea-header">
        <Link to="/past-events" className="ea-back-link">
          &larr; Past Events
        </Link>
        <h1 className="ea-title">{config.title}</h1>
        <p className="ea-subtitle">{config.semester} &mdash; Innovate to Grow</p>
      </div>

      {hasSchedule && (
        <section className="ea-section">
          <h2 className="ea-section-title">Presentation Schedule</h2>
          <ScheduleGrid
            classes={config.classes}
            rows={rows}
            trackInfos={trackInfos}
            loading={loading}
            error={error}
            onTeamClick={handleTeamClick}
          />
        </section>
      )}

      <section className="ea-section">
        <h2 className="ea-section-title">Projects &amp; Teams</h2>
        <SheetsDataTable
          key={teamSearch || 'all-projects'}
          rows={rows}
          loading={loading}
          error={error}
          initialSearch={teamSearch}
        />
      </section>
    </div>
  );
};
