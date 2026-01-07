import { useEffect, useState } from 'react';
import { fetchEvent, type EventData } from '../services/api';
import { formatEventDate } from '../utils/dateUtils';
import { renderMarkdown } from '../components/Event/markdown';
import './HomePreEvent.css';

export const HomePreEvent = () => {
  const [eventData, setEventData] = useState<EventData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchEvent();
        setEventData(data);
      } catch (err) {
        console.error(err);
        setError('Unable to load event data.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const eventDate = eventData ? formatEventDate(eventData.event_date) : null;

  return (
    <div className="home-pre-event">
      <div className="home-pre-event-hero">
        <img
          src="/i2g-header-img.jpg"
          alt="Innovate to Grow students at expo"
          className="home-pre-event-hero-img"
        />
      </div>

      <div className="home-pre-event-body">
        <section className="home-pre-event-program">
          <h2>The Innovate to Grow program</h2>
          <p>
            Innovate to Grow (I2G) is a unique “experiential learning” program that engages
            external partner organizations with teams of students who design systems to solve
            real-world problems. The Innovate to Grow program encompasses the following
            experiential learning classes: <strong>Engineering Capstone</strong>,{' '}
            <strong>Engineering Service Learning</strong>, and <strong>Software Engineering Capstone</strong>.
          </p>
        </section>

        <section className="home-pre-event-showcase">
          <div className="showcase-text">
            <h3>The I2G showcase</h3>
            <p className="showcase-date">
              {eventData ? `${eventData.event_name}: ${eventDate}` : 'Upcoming event details'}
            </p>

            {loading && <div className="showcase-state">Loading event details...</div>}
            {error && <div className="showcase-state showcase-error">{error}</div>}

            {eventData && eventData.upper_bullet_points && eventData.upper_bullet_points.length > 0 && (
              <ul className="showcase-list">
                {eventData.upper_bullet_points.map((item, index) => (
                  <li key={index} dangerouslySetInnerHTML={{ __html: renderMarkdown(item) }} />
                ))}
              </ul>
            )}

            <div className="showcase-actions">
              <button className="btn-primary">REGISTER NOW !</button>
              <button className="btn-secondary">EVENT INFO</button>
            </div>
          </div>

          <div className="showcase-video">
            <div className="video-frame">
              <iframe
                src="https://www.youtube.com/embed/oQV7O_ZFJK8"
                title="UC Merced Innovate To Grow"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
              />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

