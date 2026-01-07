import type { TrackWinner } from '../../services/api';
import './WinnersSection.css';

interface WinnersSectionProps {
  trackWinners: TrackWinner[];
  specialAwards: string[];
}

// Determine program type from track name
const getProgramFromTrack = (trackName: string): 'CAP' | 'CEE' | 'CSE' | null => {
  if (trackName.includes('Track 1') || trackName.includes('Track 2')) {
    return 'CAP';
  } else if (trackName.includes('Track 3') || trackName.includes('Civil') || trackName.includes('Environmental')) {
    return 'CEE';
  } else if (trackName.includes('Track 4') || trackName.includes('Track 5')) {
    return 'CSE';
  }
  return null;
};

// Get program display name
const getProgramDisplayName = (program: 'CAP' | 'CEE' | 'CSE'): string => {
  switch (program) {
    case 'CAP':
      return 'Engineering Capstone (CAP)';
    case 'CEE':
      return 'Civil & Environmental Track 3';
    case 'CSE':
      return 'Software Engineering Capstone (CSE)';
  }
};

// Get track category
const getTrackCategory = (trackName: string): string => {
  if (trackName.includes('Track 1')) return 'FoodTech';
  if (trackName.includes('Track 2')) return 'Precision';
  if (trackName.includes('Track 3')) return 'Environment';
  if (trackName.includes('Track 4')) return 'Tim Berners-Lee';
  if (trackName.includes('Track 5')) return 'Grace Hopper';
  return '';
};

export const WinnersSection = ({ trackWinners, specialAwards }: WinnersSectionProps) => {
  const hasTrackWinners = trackWinners && trackWinners.length > 0;
  const hasSpecialAwards = specialAwards && specialAwards.length > 0;

  if (!hasTrackWinners && !hasSpecialAwards) {
    return null;
  }

  // Group track winners by program
  const winnersByProgram = trackWinners.reduce((acc, winner) => {
    const program = getProgramFromTrack(winner.track_name);
    if (program) {
      if (!acc[program]) {
        acc[program] = [];
      }
      acc[program].push(winner);
    }
    return acc;
  }, {} as Record<'CAP' | 'CEE' | 'CSE', TrackWinner[]>);

  return (
    <div className="winners-section">
      <h2 className="winners-title">Winners! Innovate to Grow</h2>

      {/* Special Awards at Top */}
      {hasSpecialAwards && (
        <div className="special-awards-section">
          <h3 className="special-awards-title">Special Awards</h3>
          <ul className="special-awards-list">
            {specialAwards.map((award, index) => (
              <li key={index} className="special-award-item">{award}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Track Winners by Program */}
      {hasTrackWinners && (
        <div className="track-winners-section">
          {/* Engineering Capstone (CAP) */}
          {winnersByProgram.CAP && winnersByProgram.CAP.length > 0 && (
            <div className="program-winners program-cap">
              <h3 className="program-winners-title">Engineering Capstone (CAP)</h3>
              <div className="winners-table-container">
                <table className="winners-table">
                  <thead>
                    <tr>
                      {winnersByProgram.CAP.map((winner) => {
                        const isCEE = winner.track_name.includes('Track 3');
                        return (
                          <th key={winner.track_name} className={isCEE ? 'track-header-cell-cee' : 'track-header-cell'}>
                            {isCEE ? 'Civil & Environmental' : winner.track_name}
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      {winnersByProgram.CAP.map((winner) => {
                        const category = getTrackCategory(winner.track_name);
                        const isCEE = winner.track_name.includes('Track 3');
                        return (
                          <td key={`category-${winner.track_name}`} className={`winner-category-cell ${isCEE ? 'winner-cell-cee' : 'winner-cell-cap'}`}>
                            {category}
                          </td>
                        );
                      })}
                    </tr>
                    <tr>
                      {winnersByProgram.CAP.map((winner) => {
                        const isCEE = winner.track_name.includes('Track 3');
                        return (
                          <td key={`winner-${winner.track_name}`} className={`winner-name-cell ${isCEE ? 'winner-cell-cee' : 'winner-cell-cap'}`}>
                            {winner.winner_name}
                          </td>
                        );
                      })}
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Civil & Environmental (CEE) - if not already in CAP */}
          {winnersByProgram.CEE && winnersByProgram.CEE.length > 0 && !winnersByProgram.CAP?.some(w => w.track_name.includes('Track 3')) && (
            <div className="program-winners program-cee">
              <h3 className="program-winners-title">Civil & Environmental Track 3</h3>
              <div className="winners-table-container">
                <table className="winners-table">
                  <thead>
                    <tr>
                      {winnersByProgram.CEE.map((winner) => (
                        <th key={winner.track_name} className="track-header-cell-cee">
                          Civil & Environmental
                        </th>
                      ))}
                    </tr>
                    <tr>
                      {winnersByProgram.CEE.map((winner) => (
                        <th key={`track-${winner.track_name}`} className="track-header-cell-cee">
                          {winner.track_name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      {winnersByProgram.CEE.map((winner) => {
                        const category = getTrackCategory(winner.track_name);
                        return (
                          <td key={`category-${winner.track_name}`} className="winner-category-cell winner-cell-cee">
                            {category}
                          </td>
                        );
                      })}
                    </tr>
                    <tr>
                      {winnersByProgram.CEE.map((winner) => (
                        <td key={`winner-${winner.track_name}`} className="winner-name-cell winner-cell-cee">
                          {winner.winner_name}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Software Engineering Capstone (CSE) */}
          {winnersByProgram.CSE && winnersByProgram.CSE.length > 0 && (
            <div className="program-winners program-cse">
              <h3 className="program-winners-title">Software Engineering Capstone (CSE)</h3>
              <div className="winners-table-container">
                <table className="winners-table">
                  <thead>
                    <tr>
                      {winnersByProgram.CSE.map((winner) => (
                        <th key={winner.track_name} className="track-header-cell">
                          {winner.track_name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      {winnersByProgram.CSE.map((winner) => {
                        const category = getTrackCategory(winner.track_name);
                        return (
                          <td key={`category-${winner.track_name}`} className="winner-category-cell winner-cell-cse">
                            {category}
                          </td>
                        );
                      })}
                    </tr>
                    <tr>
                      {winnersByProgram.CSE.map((winner) => (
                        <td key={`winner-${winner.track_name}`} className="winner-name-cell winner-cell-cse">
                          {winner.winner_name}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};


