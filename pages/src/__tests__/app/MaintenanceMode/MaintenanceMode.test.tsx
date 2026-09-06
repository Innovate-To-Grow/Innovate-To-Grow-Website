import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {MaintenanceMode} from '@/app/MaintenanceMode/MaintenanceMode';

describe('MaintenanceMode', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the default message when none is provided', () => {
    render(<MaintenanceMode />);

    expect(screen.getByText(/temporarily down for maintenance/)).toBeInTheDocument();
  });

  it('renders a custom message', () => {
    render(<MaintenanceMode message="Custom maintenance message" />);

    expect(screen.getByText('Custom maintenance message')).toBeInTheDocument();
  });

  it('hides the bypass control unless maintenance and onBypass are both set', () => {
    render(<MaintenanceMode maintenance />);

    expect(screen.queryByRole('button', {name: 'Bypass with Password'})).not.toBeInTheDocument();
  });

  it('shows the bypass control and accepts a successful password', async () => {
    const onBypass = vi.fn().mockResolvedValue(true);
    render(<MaintenanceMode maintenance onBypass={onBypass} />);

    fireEvent.click(screen.getByRole('button', {name: 'Bypass with Password'}));
    fireEvent.change(screen.getByPlaceholderText('Enter bypass password'), {target: {value: 'secret'}});
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: 'Enter'}));
    });

    expect(onBypass).toHaveBeenCalledWith('secret');
    expect(screen.queryByText('Incorrect password.')).not.toBeInTheDocument();
  });

  it('shows an error when the bypass password is rejected', async () => {
    const onBypass = vi.fn().mockResolvedValue(false);
    render(<MaintenanceMode maintenance onBypass={onBypass} />);

    fireEvent.click(screen.getByRole('button', {name: 'Bypass with Password'}));
    fireEvent.change(screen.getByPlaceholderText('Enter bypass password'), {target: {value: 'wrong'}});
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: 'Enter'}));
    });

    expect(screen.getByText('Incorrect password.')).toBeInTheDocument();
  });

  it('shows an error when the bypass check throws', async () => {
    const onBypass = vi.fn().mockRejectedValue(new Error('network'));
    render(<MaintenanceMode maintenance onBypass={onBypass} />);

    fireEvent.click(screen.getByRole('button', {name: 'Bypass with Password'}));
    fireEvent.change(screen.getByPlaceholderText('Enter bypass password'), {target: {value: 'x'}});
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: 'Enter'}));
    });

    expect(screen.getByText('Failed to verify. Please try again.')).toBeInTheDocument();
  });

  it('does not submit with an empty password', async () => {
    const onBypass = vi.fn();
    const {container} = render(<MaintenanceMode maintenance onBypass={onBypass} />);

    fireEvent.click(screen.getByRole('button', {name: 'Bypass with Password'}));

    const form = container.querySelector('form')!;
    fireEvent.submit(form);
    await act(async () => {});

    expect(onBypass).not.toHaveBeenCalled();
  });

  it('shows a verifying label while the bypass is in flight', async () => {
    let resolve!: (value: boolean) => void;
    const onBypass = vi.fn().mockImplementation(
      () => new Promise<boolean>((next) => {
        resolve = next;
      }),
    );
    render(<MaintenanceMode maintenance onBypass={onBypass} />);

    fireEvent.click(screen.getByRole('button', {name: 'Bypass with Password'}));
    fireEvent.change(screen.getByPlaceholderText('Enter bypass password'), {target: {value: 'x'}});
    fireEvent.click(screen.getByRole('button', {name: 'Enter'}));

    expect(screen.getByRole('button', {name: 'Verifying...'})).toBeInTheDocument();

    await act(async () => {
      resolve(true);
    });
  });
});
