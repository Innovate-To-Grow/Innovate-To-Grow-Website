import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { PrivacyLegalNotice } from './PrivacyLegalNotice';

describe('PrivacyLegalNotice', () => {
  it('links users to the Privacy/Legal Notice', () => {
    render(
      <MemoryRouter>
        <PrivacyLegalNotice action="creating an account" />
      </MemoryRouter>,
    );

    expect(screen.getByText(/By creating an account/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Privacy/Legal Notice' })).toHaveAttribute('href', '/privacy');
  });
});
