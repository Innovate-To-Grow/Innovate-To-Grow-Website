import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      // Rendered outside the router (it wraps every React root), so plain links only.
      return (
        <section className="itg-empty-state app-error-boundary" role="alert">
          <h2 className="itg-empty-state-title">Something went wrong</h2>
          <p className="itg-empty-state-text">Please refresh the page or try again later.</p>
          <div className="itg-empty-state-actions">
            <button type="button" className="itg-btn itg-btn-primary" onClick={() => window.location.reload()}>
              Refresh
            </button>
            <a href="/" className="itg-link">
              Go to the home page
            </a>
          </div>
        </section>
      );
    }
    return this.props.children;
  }
}
