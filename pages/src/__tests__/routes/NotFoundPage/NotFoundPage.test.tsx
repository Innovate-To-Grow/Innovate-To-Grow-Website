import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, describe, expect, it} from 'vitest';

import {NotFoundPage} from '@/routes/NotFoundPage/NotFoundPage';

describe('NotFoundPage', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the 404 code, title, and message', () => {
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>,
    );

    expect(screen.getByText('404')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Page not found'})).toBeInTheDocument();
    expect(
      screen.getByText("The page you're looking for doesn't exist or has been moved."),
    ).toBeInTheDocument();
  });
});
