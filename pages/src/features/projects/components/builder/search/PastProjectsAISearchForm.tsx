import {useId, useState, type FormEvent} from 'react';

interface PastProjectsAISearchFormProps {
  isAuthenticated: boolean;
  loading: boolean;
  onSearch: (query: string) => Promise<void>;
}

export const PastProjectsAISearchForm = ({
  isAuthenticated,
  loading,
  onSearch,
}: PastProjectsAISearchFormProps) => {
  const inputId = useId();
  const [query, setQuery] = useState('');
  const trimmedQuery = query.trim();
  const formClassName = `project-grid-search-field past-projects-ai-search${loading ? ' is-loading' : ''}`;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!isAuthenticated || loading || !trimmedQuery) {
      return;
    }
    await onSearch(trimmedQuery);
  };

  return (
    <form
      className={formClassName}
      aria-busy={loading}
      onSubmit={(event) => void handleSubmit(event)}
    >
      <div className="itg-field past-projects-ai-search-field">
        <label className="project-grid-field-label" htmlFor={inputId}>
          AI Search
        </label>
        <span className="past-projects-ai-search-input-frame">
          <input
            id={inputId}
            type="search"
            className="itg-input project-grid-search-input past-projects-ai-search-input"
            value={query}
            placeholder="Ask AI to find relevant past projects..."
            disabled={!isAuthenticated || loading}
            onChange={(event) => setQuery(event.target.value)}
          />
        </span>
      </div>
      <button
        type="submit"
        className="itg-btn itg-btn-primary"
        disabled={!isAuthenticated || loading || !trimmedQuery}
      >
        Search
      </button>
      {loading ? (
        <p className="past-projects-ai-search-status" role="status" aria-live="polite">
          Searching past projects with AI...
        </p>
      ) : null}
    </form>
  );
};
