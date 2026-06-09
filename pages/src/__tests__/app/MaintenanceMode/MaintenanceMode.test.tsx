import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {MaintenanceMode} from '@/app/MaintenanceMode/MaintenanceMode';

describe('MaintenanceMode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the default maintenance message without bypass controls', () => {
    render(<MaintenanceMode />);

    expect(screen.getByText('Service Unavailable')).toBeInTheDocument();
    expect(screen.getByText(/temporarily down for maintenance/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Bypass with Password'})).not.toBeInTheDocument();
  });

  it('submits the bypass password and surfaces a rejected password', async () => {
    const onBypass = vi.fn().mockResolvedValue(false);

    render(<MaintenanceMode message="Deploy in progress." maintenance onBypass={onBypass} />);

    fireEvent.click(screen.getByRole('button', {name: 'Bypass with Password'}));
    const submit = screen.getByRole('button', {name: 'Enter'});
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText('Enter bypass password'), {
      target: {value: 'secret'},
    });
    fireEvent.click(submit);

    await waitFor(() => expect(onBypass).toHaveBeenCalledWith('secret'));
    expect(await screen.findByText('Incorrect password.')).toBeInTheDocument();
  });

  it('shows a verification error when bypass verification fails', async () => {
    const onBypass = vi.fn().mockRejectedValue(new Error('offline'));

    render(<MaintenanceMode maintenance onBypass={onBypass} />);

    fireEvent.click(screen.getByRole('button', {name: 'Bypass with Password'}));
    fireEvent.change(screen.getByPlaceholderText('Enter bypass password'), {
      target: {value: 'secret'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Enter'}));

    expect(await screen.findByText('Failed to verify. Please try again.')).toBeInTheDocument();
  });
});
