import {cleanup, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {RegisterPage} from '@/features/auth/components/pages/RegisterPage';

const mockGetRegisterLinkPath = vi.fn();

vi.mock('@/features/auth/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth/api')>()),
  getRegisterLinkPath: () => mockGetRegisterLinkPath(),
}));

function Landing() {
  const location = useLocation();
  return <div>{`landed:${location.pathname}${location.search}`}</div>;
}

function renderRegister() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="*" element={<Landing />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('RegisterPage', () => {
  // A block body: a function returned from beforeEach would run as a teardown (the mock itself, here).
  beforeEach(() => {
    mockGetRegisterLinkPath.mockReset();
  });
  afterEach(cleanup);

  it('goes where staff pointed /register', async () => {
    mockGetRegisterLinkPath.mockResolvedValue('/event-registration?event=fall-demo');
    renderRegister();
    expect(screen.getByRole('status')).toHaveTextContent('Opening registration...');
    expect(await screen.findByText('landed:/event-registration?event=fall-demo')).toBeInTheDocument();
  });

  it('falls back to the sign-in page when there is no answer', async () => {
    mockGetRegisterLinkPath.mockImplementation(() => Promise.reject(new Error('offline')));
    renderRegister();
    await waitFor(() => expect(screen.getByText('landed:/login')).toBeInTheDocument());
  });

  it.each([
    ['no path', () => mockGetRegisterLinkPath.mockResolvedValue(null)],
    ['an off-site path', () => mockGetRegisterLinkPath.mockResolvedValue('//evil.example')],
    ['itself', () => mockGetRegisterLinkPath.mockResolvedValue('/register/?x=1')],
  ])('falls back to the sign-in page for %s', async (_case, arrange) => {
    arrange();
    renderRegister();
    await waitFor(() => expect(screen.getByText('landed:/login')).toBeInTheDocument());
  });
});
