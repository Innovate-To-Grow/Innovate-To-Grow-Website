import {useState, useCallback} from 'react';
import {useSheetsData} from '../../hooks/useSheetsData';
import {ScheduleGrid} from '../../components/ScheduleGrid';
import {SheetsDataTable} from '../../components/SheetsDataTable';
import type {ClassConfig} from '../../components/ScheduleGrid';
import './EventPage.css';

const CLASSES: ClassConfig[] = [
  {
    code: 'CAP',
    label: 'Engineering Capstone',
    trackCount: 2,
    orderCount: 6,
    startTime: '1:00',
    slotMinutes: 30,
    trackLabels: ['FoodTech', 'Precision'],
  },
  {
    code: 'CEE',
    label: 'Civil & Environmental Engineering',
    trackCount: 1,
    orderCount: 4,
    startTime: '1:00',
    slotMinutes: 30,
    trackLabels: ['Environment'],
  },
  {
    code: 'CSE',
    label: 'Software Engineering Capstone',
    trackCount: 2,
    orderCount: 10,
    startTime: '1:00',
    slotMinutes: 20,
    trackLabels: ['Tim Berners-Lee', 'Grace Hopper'],
    accentColor: '#FFBF3C',
  },
];

export const EventPage = () => {
  const {rows, trackInfos, loading, error} = useSheetsData({slug: 'current-event'});

  const [, setSearchTrigger] = useState(0);

  const handleTeamClick = useCallback((teamNum: string) => {
    const projectsSection = document.getElementById('projects');
    if (projectsSection) {
      projectsSection.scrollIntoView({behavior: 'smooth'});
    }
    // Set the search input value in the SheetsDataTable
    const searchInput = projectsSection?.querySelector<HTMLInputElement>('.sdt-search');
    if (searchInput) {
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value',
      )?.set;
      nativeInputValueSetter?.call(searchInput, teamNum);
      searchInput.dispatchEvent(new Event('input', {bubbles: true}));
      searchInput.dispatchEvent(new Event('change', {bubbles: true}));
      setSearchTrigger((prev) => prev + 1);
    }
  }, []);

  return (
    <div className="event-page">
      <h1 className="event-page-title">Innovate to Grow Event</h1>

      <div className="event-page-content">
        <p className="event-page-lead">
          The Innovate to Grow event is the culminating showcase of UC Merced student innovation,
          featuring live presentations from Engineering Capstone, Software Engineering Capstone, and
          Civil &amp; Environmental Engineering teams.
        </p>

        <p className="event-page-text">
          During the event, student teams present their semester-long projects to judges, industry
          partners, and community members. Each team delivers a presentation in their assigned track
          and time slot. Browse the schedule below to see the presentation order, and click on any
          team to view their project details.
        </p>
      </div>

      <section className="event-page-section">
        <h2 className="event-page-section-title">Presentation Schedule</h2>
        <ScheduleGrid
          classes={CLASSES}
          rows={rows}
          trackInfos={trackInfos}
          loading={loading}
          error={error}
          onTeamClick={handleTeamClick}
        />
      </section>

      <section className="event-page-section">
        <h2 className="event-page-section-title">Projects &amp; Teams</h2>
        <SheetsDataTable rows={rows} loading={loading} error={error} />
      </section>
    </div>
  );
};
