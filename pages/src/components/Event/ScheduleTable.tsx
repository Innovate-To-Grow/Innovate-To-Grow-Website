import type { Program, Track, Presentation } from '../../services/api';
import './ScheduleTable.css';

interface ScheduleTableProps {
  programs: Program[];
}

// Time calculation utility - returns 12-hour format with AM/PM
// Uses track start_time if available, otherwise falls back to calculated time
const calculateTime = (order: number, track: Track, programName: string, baseHour = 13): string => {
  // CSE uses 20-minute intervals, others use 30-minute intervals
  const intervalMinutes = programName.includes('Software') || programName.includes('CSE') ? 20 : 30;
  
  // If track has a start_time, use it as the base
  if (track.start_time) {
    // Parse the start_time (format: "HH:mm:ss" or "HH:mm")
    const [hours, minutes] = track.start_time.split(':').map(Number);
    const baseMinutes = hours * 60 + minutes;
    const totalMinutes = baseMinutes + (order - 1) * intervalMinutes;
    const hour24 = Math.floor(totalMinutes / 60) % 24;
    const mins = totalMinutes % 60;
    const hour12 = hour24 > 12 ? hour24 - 12 : (hour24 === 0 ? 12 : hour24);
    const ampm = hour24 >= 12 ? 'PM' : 'AM';
    return `${hour12}:${mins.toString().padStart(2, '0')} ${ampm}`;
  }
  
  // Fallback to old calculation if no start_time
  const totalMinutes = (order - 1) * intervalMinutes;
  const hour24 = baseHour + Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const hour12 = hour24 > 12 ? hour24 - 12 : (hour24 === 0 ? 12 : hour24);
  const ampm = hour24 >= 12 ? 'PM' : 'AM';
  return `${hour12}:${minutes.toString().padStart(2, '0')} ${ampm}`;
};

// Get program color class
const getProgramColorClass = (programName: string): string => {
  // Check for CSE first (most specific)
  if (programName.includes('CSE') || programName.includes('Software') || programName.includes('Sofware')) {
    return 'program-cse';
  } else if (programName.includes('Civil') || programName.includes('CEE')) {
    return 'program-cee';
  } else if (programName.includes('Engineering Capstone') || programName.includes('CAP')) {
    return 'program-cap';
  }
  return '';
};

// Get all unique time slots across all tracks in a program
const getAllTimeSlots = (tracks: Track[]): number[] => {
  const orders = new Set<number>();
  tracks.forEach(track => {
    track.presentations.forEach(p => orders.add(p.order));
  });
  return Array.from(orders).sort((a, b) => a - b);
};

// Get presentation for a specific track and order
const getPresentation = (track: Track, order: number): Presentation | null => {
  return track.presentations.find(p => p.order === order) || null;
};

export const ScheduleTable = ({ programs }: ScheduleTableProps) => {
  if (!programs || programs.length === 0) {
    return null;
  }

  return (
    <div className="schedule-table-container">
      <h2 className="presentations-title">PRESENTATIONS</h2>
      {programs.map((program) => {
        const programColorClass = getProgramColorClass(program.program_name);
        const timeSlots = getAllTimeSlots(program.tracks);
        
        // Group tracks by room
        const tracksByRoom = program.tracks.reduce((acc, track) => {
          if (!acc[track.room]) {
            acc[track.room] = [];
          }
          acc[track.room].push(track);
          return acc;
        }, {} as Record<string, Track[]>);

        const rooms = Object.keys(tracksByRoom);
        const allTracks = program.tracks;

        return (
          <div key={program.program_name} className={`program-schedule ${programColorClass}`}>
            <h3 className="program-title">{program.program_name}</h3>
            
            <table className="schedule-table">
              <thead>
                {/* Row 1: Room header row */}
                <tr className="schedule-header-row">
                  <th className="time-header">Rooms</th>
                  {rooms.map((room) => {
                    const roomTracks = tracksByRoom[room];
                    return (
                      <th 
                        key={room} 
                        className="room-header" 
                        colSpan={roomTracks.length}
                      >
                        {room}
                      </th>
                    );
                  })}
                </tr>
                
                {/* Row 2: Track number row */}
                <tr className="schedule-header-row">
                  <th className="time-header"></th>
                  {allTracks.map((track, index) => (
                    <th key={`track-num-${track.track_name}`} className="track-header">
                      Track {index + 1}
                    </th>
                  ))}
                </tr>
                
                {/* Row 3: Track name row */}
                <tr className="schedule-header-row">
                  <th className="time-header"></th>
                  {allTracks.map((track) => (
                    <th key={`track-name-${track.track_name}`} className="category-header">
                      {track.track_name}
                    </th>
                  ))}
                </tr>
              </thead>
              
              <tbody>
                {timeSlots.map((order) => {
                  // Use the first track's time calculation for the row header
                  // In practice, all tracks in a program should have the same start_time
                  const firstTrack = allTracks[0];
                  const timeString = calculateTime(order, firstTrack, program.program_name);
                  return (
                    <tr key={order} className="schedule-row">
                      <td className="time-cell">{timeString}</td>
                      {allTracks.map((track) => {
                        const presentation = getPresentation(track, order);
                        const isBreak = presentation?.project_title?.toLowerCase().includes('break') || 
                                       presentation?.organization?.toLowerCase() === 'break';
                        
                        return (
                          <td 
                            key={`${track.track_name}-${order}`} 
                            className="presentation-cell"
                          >
                            {presentation ? (
                              isBreak ? (
                                <div className="presentation-break-content">Break</div>
                              ) : (
                                <>
                                  {presentation.team_id && (
                                    <div className="presentation-team-id">{presentation.team_id}</div>
                                  )}
                                  {presentation.organization && (
                                    <div className="presentation-org">{presentation.organization}</div>
                                  )}
                                </>
                              )
                            ) : null}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
};

