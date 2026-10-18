import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, describe, expect, it} from 'vitest';

import {NotFoundPage} from '@/routes/NotFoundPage/NotFoundPage';

describe('NotFoundPage', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the page title, the error code as its meta line, and the message as an empty state', () => {
    const {container} = render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>,
    );

    const title = screen.getByRole('heading', {name: 'Page not found', level: 1});
    const code = screen.getByText('Error 404');
    expect(title).toHaveClass('itg-page-title');
    expect(code).toHaveClass('itg-page-meta');
    // The title comes first, like every other page head; the code is the meta line under it.
    expect(title.compareDocumentPosition(code) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(
      screen.getByText("The page you're looking for doesn't exist or has been moved."),
    ).toBeInTheDocument();
    expect(container.querySelector('.itg-empty-state')).not.toBeNull();
  });

  it('offers a way back to the home page and the projects', () => {
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', {name: 'Go to the home page'})).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', {name: 'Browse projects'})).toHaveAttribute('href', '/projects');
  });
});
