
import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router';

import {AuthProvider} from '@/features/auth/components/AuthContext';
import {LoginLinkPage} from '@/routes/auth/LoginLinkPage/LoginLinkPage';
import {seedHandoff} from '@/__tests__/routes/auth/LoginLinkPage/integration/fixtures/loginLinkIntegrationFixtures';
import {GOOD_CODE} from '@/__tests__/routes/auth/LoginLinkPage/integration/fixedBackend/fixedBackendIntegrationSetup';

export const renderApp = () =>
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/login-link']}>
        <Routes>
          <Route path="/login-link" element={<LoginLinkPage />} />
          <Route path="/login" element={<p>Login route</p>} />
          <Route path="/verify-email" element={<p>Verify-email route</p>} />
          <Route path="/schedule" element={<p>Schedule page</p>} />
          <Route path="/account" element={<p>Account page</p>} />
          <Route path="/complete-profile" element={<p>Complete-profile page</p>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );

export const openLink = async (token: string) => {
  seedHandoff(token);
  const view = renderApp();
  await screen.findByLabelText('Email address');
  return view;
};

export const typeEmailAndSend = async (email = 'New@Example.com') => {
  fireEvent.change(screen.getByLabelText('Email address'), {target: {value: email}});
  fireEvent.click(screen.getByRole('button', {name: 'Send sign-in code'}));
  await screen.findByRole('textbox', {name: '6-digit verification code'});
};

export const typeCodeAndContinue = (code = GOOD_CODE) => {
  fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: code}});
  fireEvent.click(screen.getByRole('button', {name: 'Verify and Sign In'}));
};
