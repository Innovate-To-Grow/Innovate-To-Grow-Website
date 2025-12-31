import type { Program, Track, Presentation } from '../../services/api';
import './ScheduleTable.css';

interface ScheduleTableProps {
  programs: Program[];
}

// Track category mapping
const TRACK_CATEGORIES: Record<string, string> = {
  'Track 1': 'AgTech',
  'Track 2': 'FoodTech',
  'Track 3': 'Environment',
  'Track 4': 'Tim Berners-Lee',
  'Track 5': 'Grace Hopper',
};

// Time calculation utility
const calculateTime = (order: number, programName: string, baseHour = 13): string => {
  // CSE uses 20-minute intervals, others use 30-minute intervals
  const intervalMinutes = programName.includes('Software') || programName.includes('CSE') ? 20 : 30;
  const totalMinutes = (order - 1) * intervalMinutes;
  const hour = baseHour + Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${hour}:${minutes.toString().padStart(2, '0')}`;
};

// Get program color class
const getProgramColorClass = (programName: string): string => {
  if (programName.includes('Engineering Capstone') || programName.includes('CAP')) {
    return 'program-cap';
  } else if (programName.includes('Civil') || programName.includes('CEE')) {
    return 'program-cee';
  } else if (programName.includes('Software') || programName.includes('CSE')) {
    return 'program-cse';
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
                {/* Room header row */}
                <tr className="schedule-header-row">
                  <th className="time-header">Time</th>
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
                
                {/* Track header row */}
                <tr className="schedule-header-row">
                  <th className="time-header">Track</th>
                  {allTracks.map((track) => (
                    <th key={track.track_name} className="track-header">
                      {track.track_name}
                    </th>
                  ))}
                </tr>
                
                {/* Category header row */}
                <tr className="schedule-header-row">
                  <th className="time-header"></th>
                  {allTracks.map((track) => {
                    const category = TRACK_CATEGORIES[track.track_name] || '';
                    return (
                      <th key={`category-${track.track_name}`} className="category-header">
                        {category}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              
              <tbody>
                {timeSlots.map((order) => {
                  const timeString = calculateTime(order, program.program_name);
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
                            className={`presentation-cell ${isBreak ? 'break-cell' : ''}`}
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

