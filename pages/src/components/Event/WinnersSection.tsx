import type { TrackWinner, SpecialAward } from '../../services/api';
import './WinnersSection.css';

interface WinnersSectionProps {
  trackWinners: TrackWinner[];
  specialAwards: SpecialAward[];
}

export const WinnersSection = ({ trackWinners, specialAwards }: WinnersSectionProps) => {
  const hasTrackWinners = trackWinners && trackWinners.length > 0;
  const hasSpecialAwards = specialAwards && specialAwards.length > 0;

  if (!hasTrackWinners && !hasSpecialAwards) {
    return null;
  }

  return (
    <div className="winners-section">
      <h2 className="winners-title">Winners & Awards</h2>

      {hasTrackWinners && (
        <div className="track-winners-section">
          <h3 className="winners-subtitle">Track Winners</h3>
          <div className="track-winners-grid">
            {trackWinners.map((winner, index) => (
              <div key={`${winner.track_name}-${index}`} className="winner-card">
                <div className="winner-track">{winner.track_name}</div>
                <div className="winner-name">{winner.winner_name}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {hasSpecialAwards && (
        <div className="special-awards-section">
          <h3 className="winners-subtitle">Special Awards</h3>
          <div className="special-awards-list">
            {specialAwards.map((award, index) => (
              <div key={`${award.program_name}-${index}`} className="award-card">
                <div className="award-program">{award.program_name}</div>
                <div className="award-winner">{award.award_winner}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

