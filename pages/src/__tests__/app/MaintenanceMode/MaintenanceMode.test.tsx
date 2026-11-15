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

  it('renders the UC Merced maintenance card around the message', () => {
    const {container} = render(<MaintenanceMode />);

    const title = screen.getByRole('heading', {name: 'Service Unavailable', level: 1});
    expect(container.querySelector('.maintenance-card')).toContainElement(title);
    expect(container.querySelector('.maintenance-alert')).toContainElement(screen.getByRole('status'));
    expect(container.querySelector('.maintenance-gear svg')).toBeInTheDocument();
    expect(screen.getByAltText('UC Merced')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'What happened?'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'What can I do?'})).toBeInTheDocument();
  });

  it('does not add a main landmark of its own inside the shell main', () => {
    // The overlay renders inside #root, which sits in the page's <main id="main">.
    const shellMain = document.createElement('main');
    document.body.appendChild(shellMain);
    const {container} = render(<MaintenanceMode />, {container: shellMain});

    expect(screen.getAllByRole('main')).toEqual([shellMain]);
    expect(container.querySelector('main main, main [role="main"]')).toBeNull();
    expect(container.querySelector('.maintenance-content')?.tagName).toBe('DIV');
    shellMain.remove();
  });

  it('labels the bypass field and reports its open state', () => {
    render(<MaintenanceMode maintenance onBypass={vi.fn()} />);

    const toggle = screen.getByRole('button', {name: 'Bypass with Password'});
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByLabelText('Bypass password')).toHaveAttribute('type', 'password');
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
