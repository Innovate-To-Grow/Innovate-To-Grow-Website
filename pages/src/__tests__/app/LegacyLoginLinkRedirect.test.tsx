import {render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {describe, expect, it} from 'vitest';

import {LegacyLoginLinkRedirect} from '@/app/LegacyLoginLinkRedirect';

describe('LegacyLoginLinkRedirect', () => {
  it('redirects legacy token links to /login-link while preserving the query string', () => {
    render(
      <MemoryRouter initialEntries={['/magic-login?token=abc123']}>
        <Routes>
          <Route path="/magic-login" element={<LegacyLoginLinkRedirect />} />
          <Route path="/login-link" element={<div>Login link destination</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Login link destination')).toBeInTheDocument();
  });
});
