import {useState, type FormEvent} from 'react';

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
  const [query, setQuery] = useState('');
  const trimmedQuery = query.trim();

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!isAuthenticated || loading || !trimmedQuery) {
      return;
    }
    await onSearch(trimmedQuery);
  };

  return (
    <form className="project-grid-search-field past-projects-ai-search" onSubmit={(event) => void handleSubmit(event)}>
      <label className="past-projects-ai-search-field">
        <span className="project-grid-field-label">AI Search</span>
        <input
          type="search"
          className="project-grid-search-input past-projects-ai-search-input"
          value={query}
          placeholder="Ask AI to find relevant past projects..."
          disabled={!isAuthenticated || loading}
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>
      <button
        type="submit"
        className="itg-btn itg-btn-primary"
        disabled={!isAuthenticated || loading || !trimmedQuery}
      >
        {loading ? 'Searching...' : 'Search'}
      </button>
    </form>
  );
};
