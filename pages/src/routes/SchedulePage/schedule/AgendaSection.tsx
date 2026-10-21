import type {ScheduleAgendaSection} from '@/features/events/api';

/** A titled agenda table (the expo, the awards ceremony); renders nothing without items. */
export const AgendaSection = ({agenda, embedSection}: {agenda: ScheduleAgendaSection; embedSection: string}) =>
  agenda.items.length > 0 ? (
    <section className="schedule-page-section" data-embed-section={embedSection}>
      <h2 className="itg-section-title schedule-page-section-title">{agenda.title}</h2>
      <div className="schedule-page-agenda-wrap">
        <table className="schedule-page-agenda-table">
          <thead>
            <tr>
              <th scope="col">Room:</th>
              <th scope="col">{agenda.location}</th>
            </tr>
          </thead>
          <tbody>
            {agenda.items.map((item) => (
              <tr key={item.id}>
                <th scope="row">{item.time}</th>
                <td>{item.title}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  ) : null;
