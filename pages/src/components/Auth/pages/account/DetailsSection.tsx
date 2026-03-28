interface DetailsSectionProps {
  displayEmail?: string | null;
  dateJoined?: string | null;
}

export const DetailsSection = ({displayEmail, dateJoined}: DetailsSectionProps) => (
  <div className="account-section">
    <h2 className="account-section-title">Account Details</h2>

    <div className="account-details-rows">
      <div className="account-readonly-group">
        <span className="auth-form-label">Email</span>
        <span className="account-readonly-value">{displayEmail}</span>
      </div>

      {dateJoined ? (
        <div className="account-readonly-group">
          <span className="auth-form-label">Member Since</span>
          <span className="account-readonly-value">{new Date(dateJoined).toLocaleDateString()}</span>
        </div>
      ) : null}
    </div>
  </div>
);
