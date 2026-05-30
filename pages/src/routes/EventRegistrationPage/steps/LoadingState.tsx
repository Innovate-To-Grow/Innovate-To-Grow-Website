interface LoadingStateProps {
  error: string | null;
}

export const LoadingState = ({error}: LoadingStateProps) => {
  if (error) {
    return (
      <div className="event-reg-page">
        <h1 className="event-reg-title">Event Registration</h1>
        <div className="event-reg-alert error">{error}</div>
      </div>
    );
  }

  return (
    <div className="event-reg-page">
      <div className="event-reg-loading">Loading event details...</div>
    </div>
  );
};
