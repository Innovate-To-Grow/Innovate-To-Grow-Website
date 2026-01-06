import { useState, useEffect, useMemo } from 'react';
import { fetchEvent, type EventData, type Program, type TrackWinner, type SpecialAward } from '../services/api';
import { ScheduleTable } from '../components/Event/ScheduleTable';
import { DataTable } from '../components/Event/DataTable';
import './HomePostEvent.css';

interface ProgramWinners {
  program: Program;
  trackWinners: TrackWinner[];
  specialAward: SpecialAward | null;
}

export const HomePostEvent = () => {
  const [eventData, setEventData] = useState<EventData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadEventData = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchEvent();
        setEventData(data);
      } catch (err) {
        setError('Unable to load event data.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    loadEventData();
  }, []);

  // Map track winners to programs by matching track_name
  const programWinners = useMemo(() => {
    if (!eventData || !eventData.programs || !eventData.track_winners) {
      return [];
    }

    return eventData.programs.map((program): ProgramWinners => {
      // Find all tracks in this program
      const programTrackNames = new Set(
        program.tracks.map(track => track.track_name)
      );

      // Find track winners that belong to this program
      const trackWinners = eventData.track_winners.filter(winner =>
        programTrackNames.has(winner.track_name)
      );

      // Find special award for this program
      const specialAward = eventData.special_awards?.find(
        award => award.program_name === program.program_name
      ) || null;

      return {
        program,
        trackWinners,
        specialAward,
      };
    }).filter(pw => pw.trackWinners.length > 0 || pw.specialAward !== null);
  }, [eventData]);

  if (loading) {
    return (
      <div className="home-post-event-container">
        <div className="home-post-event-state">Loading event data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="home-post-event-container">
        <div className="home-post-event-state home-post-event-error">{error}</div>
      </div>
    );
  }

  if (!eventData) {
    return null;
  }

  const hasWinners = programWinners.length > 0;
  const allSpecialAwards = eventData.special_awards || [];

  return (
    <div className="home-post-event-container">
      {/* Winners Section */}
      {hasWinners && (
        <div className="winners-section">
          <h2 className="winners-title">Winners! Innovate to Grow</h2>
          
          {/* Special Awards Text - Right below title */}
          {allSpecialAwards.length > 0 && (
            <div className="special-awards-text">
              {allSpecialAwards.map((award, index) => (
                <div key={index} className="special-award-item">
                  <strong>{award.program_name} - Program Special Award Winner:</strong> {award.award_winner}
                </div>
              ))}
            </div>
          )}
          
          <div className="winners-grid">
            {programWinners.map((programWinner) => {
              const { program, trackWinners } = programWinner;
              const programColorClass = getProgramColorClass(program.program_name);

              return (
                <div key={program.program_name} className={`program-winners-column ${programColorClass}`}>
                  {/* Program Header */}
                  <h3 className="program-winners-header">{program.program_name}</h3>

                  {/* Track Winners Table */}
                  {trackWinners.length > 0 && (
                    <div className="track-winners-table-container">
                      <table className="track-winners-table">
                        <thead>
                          <tr>
                            <th>Track</th>
                            <th>Winning Team</th>
                          </tr>
                        </thead>
                        <tbody>
                          {trackWinners.map((winner) => (
                            <tr key={winner.track_name}>
                              <td className="track-cell">{winner.track_name}</td>
                              <td className="winner-cell">{winner.winner_name}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Schedule Section */}
      {eventData.programs && eventData.programs.length > 0 && (
        <ScheduleTable programs={eventData.programs} />
      )}

      {/* Projects Data Table Section */}
      {eventData.programs && eventData.programs.length > 0 && (
        <DataTable programs={eventData.programs} />
      )}
    </div>
  );
};

// Helper function to get program color class (matching ScheduleTable logic)
const getProgramColorClass = (programName: string): string => {
  if (programName.includes('CSE') || programName.includes('Software') || programName.includes('Sofware')) {
    return 'program-cse';
  } else if (programName.includes('Civil') || programName.includes('CEE')) {
    return 'program-cee';
  } else if (programName.includes('Engineering Capstone') || programName.includes('CAP')) {
    return 'program-cap';
  }
  return '';
};

