import { useState } from 'react';
import type { Program, Track } from '../../services/api';
import './ScheduleTable.css';

interface ScheduleTableProps {
  programs: Program[];
}

export const ScheduleTable = ({ programs }: ScheduleTableProps) => {
  const [selectedProgramIndex, setSelectedProgramIndex] = useState(0);

  if (!programs || programs.length === 0) {
    return null;
  }

  const selectedProgram = programs[selectedProgramIndex];

  // Group tracks by room for column layout
  const tracksByRoom = selectedProgram.tracks.reduce((acc, track) => {
    if (!acc[track.room]) {
      acc[track.room] = [];
    }
    acc[track.room].push(track);
    return acc;
  }, {} as Record<string, Track[]>);

  const rooms = Object.keys(tracksByRoom);

  return (
    <div className="schedule-table-container">
      <h2 className="schedule-title">Schedule</h2>

      {/* Program Tabs */}
      {programs.length > 1 && (
        <div className="program-tabs">
          {programs.map((program, index) => (
            <button
              key={program.program_name}
              className={`program-tab ${index === selectedProgramIndex ? 'active' : ''}`}
              onClick={() => setSelectedProgramIndex(index)}
            >
              {program.program_name}
            </button>
          ))}
        </div>
      )}

      {/* Schedule Grid */}
      <div className="schedule-grid">
        {rooms.map((room) => (
          <div key={room} className="track-column">
            <h3 className="room-name">{room}</h3>
            {tracksByRoom[room].map((track) => (
              <div key={track.track_name} className="track-section">
                <h4 className="track-name">{track.track_name}</h4>
                <div className="presentations-list">
                  {track.presentations
                    .sort((a, b) => a.order - b.order)
                    .map((presentation) => {
                      // Check if this is a Break entry
                      const isBreak = presentation.project_title?.toLowerCase().includes('break') || 
                                     presentation.organization?.toLowerCase() === 'break';
                      
                      return (
                        <div 
                          key={`${track.track_name}-${presentation.order}`} 
                          className={`presentation-card ${isBreak ? 'presentation-break' : ''}`}
                        >
                          <div className="presentation-order">#{presentation.order}</div>
                          <div className="presentation-content">
                            {isBreak ? (
                              // Break display
                              <>
                                <div className="presentation-team presentation-break-label">Break</div>
                                <div className="presentation-title">{presentation.project_title}</div>
                              </>
                            ) : (
                              // Regular presentation display
                              <>
                                {presentation.team_name && (
                                  <div className="presentation-team">{presentation.team_name}</div>
                                )}
                                <div className="presentation-title">{presentation.project_title}</div>
                                {presentation.organization && (
                                  <div className="presentation-org">{presentation.organization}</div>
                                )}
                                {presentation.team_id && (
                                  <div className="presentation-id">ID: {presentation.team_id}</div>
                                )}
                              </>
                            )}
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
};

