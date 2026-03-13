import {Link} from 'react-router-dom';
import './PastEventsPage.css';

const PAST_EVENTS = [
  {to: '/events/2025-fall', label: 'Fall 2025'},
  {to: '/events/2025-spring', label: 'Spring 2025'},
  {to: '/events/2024-fall', label: 'Fall 2024'},
  {to: '/events/2024-spring', label: 'Spring 2024'},
  {to: '/events/2023-fall', label: 'Fall 2023'},
  {to: '/events/2023-spring', label: 'Spring 2023'},
  {to: '/events/2022-fall', label: 'Fall 2022'},
  {to: '/events/2022-spring', label: 'Spring 2022'},
  {to: '/events/2021-fall', label: 'Fall 2021'},
  {to: '/events/2021-spring', label: 'Spring 2021'},
  {to: '/events/2020-fall', label: 'Fall 2020'},
];

export const PastEventsPage = () => {
  return (
    <div className="past-events-page">
      <h1 className="past-events-page-title">Past Events</h1>

      <p className="past-events-page-text">
        The Innovate to Grow event has been held every semester since Fall 2012, showcasing UC
        Merced student innovation in engineering and computer science. Browse the archive of past
        events below to see the teams, projects, and schedules from previous semesters.
      </p>

      <section className="past-events-page-section">
        <h2 className="past-events-page-section-title">Event Archive</h2>
        <ul className="past-events-page-list">
          {PAST_EVENTS.map((event) => (
            <li key={event.to} className="past-events-page-list-item">
              <Link to={event.to} className="past-events-page-link">
                {event.label}
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
};
