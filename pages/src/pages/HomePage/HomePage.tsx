import {useState} from 'react';
import {Link} from 'react-router-dom';
import {useLayout} from '../../components/Layout';
import {useSheetsData} from '../../hooks/useSheetsData';
import {ScheduleGrid} from '../../components/ScheduleGrid';
import {SheetsDataTable} from '../../components/SheetsDataTable';
import {SCHEDULE_CLASS_CONFIGS} from '../../config/scheduleConfig';
import './HomePage.css';

const HeroBanner = () => (
  <div className="home-hero">
    <h1 className="home-hero-title">Innovate to Grow</h1>
    <p className="home-hero-subtitle">
      UC Merced School of Engineering's Experiential Learning Program
    </p>
  </div>
);

const QuickLinks = () => (
  <div className="home-quick-links">
    <Link to="/project-submission" className="home-btn home-btn-gold">Submit a Project</Link>
    <Link to="/about" className="home-btn home-btn-blue">Learn More</Link>
    <Link to="/news" className="home-btn home-btn-gold">News</Link>
  </div>
);

const AboutSummary = () => (
  <div className="home-about">
    <h2 className="home-section-title">Engineering Solutions for Innovative Organizations</h2>
    <p className="home-text">
      Innovate to Grow (I2G) is a unique "experiential learning" program that engages external
      partner organizations with teams of students who design systems to solve complex, real-world
      problems. At the end of each semester, the work completed by the student teams culminates in the
      Innovate to Grow event.
    </p>
    <div className="home-cta-row">
      <Link to="/partnership" className="home-link">Partnership Opportunities</Link>
      <Link to="/sponsorship" className="home-link">Sponsorship</Link>
      <Link to="/faqs" className="home-link">FAQs</Link>
    </div>
  </div>
);

/** Pre-event: event not yet announced, just general info */
const PreEventContent = () => (
  <>
    <HeroBanner />
    <QuickLinks />
    <AboutSummary />
    <div className="home-notice">
      <h2 className="home-section-title">Stay Tuned!</h2>
      <p className="home-text">
        The next Innovate to Grow event date will be announced soon. Check back for updates or sign
        up for our newsletter.
      </p>
    </div>
  </>
);

/** During semester: classes in progress, event date set */
const DuringSemesterContent = () => (
  <>
    <HeroBanner />
    <QuickLinks />
    <AboutSummary />
    <div className="home-notice">
      <h2 className="home-section-title">Semester in Progress</h2>
      <p className="home-text">
        Student teams are currently working on their projects. Visit{' '}
        <Link to="/current-projects">Current Projects</Link> to see this semester's teams.
      </p>
    </div>
  </>
);

/** During/post event: show schedule grid + data table */
const EventContent = ({label}: {label: string}) => {
  const {sheets_data} = useLayout();
  const prefetched = sheets_data?.['current-event'];
  const fetched = useSheetsData({slug: prefetched ? '' : 'current-event'});

  const rows = prefetched ? prefetched.rows : fetched.rows;
  const trackInfos = prefetched ? prefetched.track_infos : fetched.trackInfos;
  const loading = prefetched ? false : fetched.loading;
  const error = prefetched ? null : fetched.error;
  const [searchFilter, setSearchFilter] = useState('');

  const handleTeamClick = (teamPrefix: string) => {
    setSearchFilter(teamPrefix);
    document.getElementById('projects')?.scrollIntoView({behavior: 'smooth'});
  };

  return (
    <>
      <HeroBanner />
      <QuickLinks />

      <div className="home-event-info">
        <h2 className="home-section-title">{label}</h2>
        <div className="home-event-links">
          <Link to="/event">Event Details</Link>
          <Link to="/schedule">Full Schedule</Link>
          <Link to="/projects-teams">All Projects & Teams</Link>
          <Link to="/judges">Judge Info</Link>
          <Link to="/attendees">Attendee Info</Link>
        </div>
      </div>

      <div className="home-schedule-section">
        <h2 className="home-section-title">Presentation Schedule</h2>
        <ScheduleGrid
          classes={SCHEDULE_CLASS_CONFIGS}
          rows={rows}
          trackInfos={trackInfos}
          loading={loading}
          error={error}
          onTeamClick={handleTeamClick}
        />
      </div>

      <div className="home-projects-section">
        <h2 className="home-section-title">Projects & Teams</h2>
        <SheetsDataTable rows={searchFilter ? rows.filter(r => r['Team#'].startsWith(searchFilter)) : rows} loading={loading} error={error} />
      </div>
    </>
  );
};

export const HomePage = () => {
  const {homepage_mode, state} = useLayout();
  const mode = homepage_mode ?? 'post-event';

  if (state === 'loading') {
    return <div className="home-page"><div className="home-loading">Loading...</div></div>;
  }

  return (
    <div className="home-page">
      {mode === 'pre-event' && <PreEventContent />}
      {mode === 'during-semester' && <DuringSemesterContent />}
      {mode === 'during-event' && <EventContent label="Live Event" />}
      {mode === 'post-event' && <EventContent label="Event Results" />}
    </div>
  );
};
