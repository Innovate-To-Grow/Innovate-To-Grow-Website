interface LoadingStateProps {
  error: string | null;
}

export const LoadingState = ({error}: LoadingStateProps) => {
  if (error) {
    return (
      <div className="event-reg-page">
        <h1 className="itg-page-title event-reg-title">Event Registration</h1>
        <div className="event-reg-alert error" role="alert">{error}</div>
      </div>
    );
  }

  return (
    <div className="event-reg-page">
      <p className="event-reg-loading" role="status">Loading event details...</p>
    </div>
  );
};
