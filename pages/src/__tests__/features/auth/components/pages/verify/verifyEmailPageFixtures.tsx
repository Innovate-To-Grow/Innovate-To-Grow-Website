import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';

import {VerifyEmailPage} from '@/features/auth/components/pages/verify/VerifyEmailPage';

export const renderPage = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/login" element={<div>login-route</div>} />
        <Route path="/account" element={<div>account-route</div>} />
        <Route path="/complete-profile" element={<div>complete-profile-route</div>} />
        <Route path="/forgot-password" element={<div>forgot-password-route</div>} />
        <Route path="/past-projects" element={<div>past-projects-route</div>} />
        <Route path="/event-registration" element={<div>event-registration-route</div>} />
      </Routes>
    </MemoryRouter>,
  );

export const enterCodeAndSubmit = (buttonName: string) => {
  fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {
    target: {value: '123456'},
  });
  fireEvent.click(screen.getByRole('button', {name: buttonName}));
};
