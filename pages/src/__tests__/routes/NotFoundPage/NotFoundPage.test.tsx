import {render, screen} from '@testing-library/react';
import {describe, expect, it} from 'vitest';

import {NotFoundPage} from '@/routes/NotFoundPage/NotFoundPage';

describe('NotFoundPage', () => {
  it('renders the 404 not found message', () => {
    render(<NotFoundPage />);

    expect(screen.getByText('404')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Page not found'})).toBeInTheDocument();
  });
});
