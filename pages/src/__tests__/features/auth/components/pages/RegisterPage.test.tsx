import {cleanup, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';
import {afterEach, describe, expect, it} from 'vitest';

import {RegisterPage} from '@/features/auth/components/pages/RegisterPage';

describe('RegisterPage', () => {
  afterEach(cleanup);

  it('navigates to /login with replace', () => {
    render(
      <MemoryRouter initialEntries={['/register']}>
        <Routes>
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/login" element={<div>login-page</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('login-page')).toBeInTheDocument();
  });
});
