import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

const api = vi.hoisted(() => ({
  bypassMaintenance: vi.fn(),
  checkHealth: vi.fn(),
}));

vi.mock('@/lib/api', () => api);

import {HealthCheckProvider} from '@/app/MaintenanceMode/HealthCheckProvider';

const healthy = {
  status: 'healthy',
  isHealthy: true,
  maintenance: false,
  maintenanceMessage: '',
};
const unhealthy = {
  status: 'maintenance',
  isHealthy: false,
  maintenance: true,
  maintenanceMessage: 'Scheduled database maintenance',
};

describe('HealthCheckProvider', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    sessionStorage.clear();
    api.checkHealth.mockResolvedValue(healthy);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  async function runInitialCheck() {
    await act(async () => {
      await vi.runOnlyPendingTimersAsync();
    });
  }

  it('renders children optimistically and keeps them after a healthy check', async () => {
    render(
      <HealthCheckProvider>
        <div>application content</div>
      </HealthCheckProvider>,
    );

    expect(screen.getByText('application content')).toBeInTheDocument();
    await runInitialCheck();
    expect(screen.getByText('application content')).toBeInTheDocument();
    expect(api.checkHealth).toHaveBeenCalledOnce();
  });

  it('shows the backend maintenance message after an unhealthy check', async () => {
    api.checkHealth.mockResolvedValue(unhealthy);
    render(
      <HealthCheckProvider>
        <div>application content</div>
      </HealthCheckProvider>,
    );

    await runInitialCheck();

    expect(screen.getByText('Service Unavailable')).toBeInTheDocument();
    expect(
      screen.getByText('Scheduled database maintenance'),
    ).toBeInTheDocument();
    expect(screen.queryByText('application content')).not.toBeInTheDocument();
  });

  it('accepts a maintenance bypass and persists it for this browser session', async () => {
    api.checkHealth.mockResolvedValue(unhealthy);
    api.bypassMaintenance.mockResolvedValue({success: true});
    render(
      <HealthCheckProvider>
        <div>application content</div>
      </HealthCheckProvider>,
    );
    await runInitialCheck();

    fireEvent.click(screen.getByRole('button', {name: 'Bypass with Password'}));
    fireEvent.change(screen.getByPlaceholderText('Enter bypass password'), {
      target: {value: 'temporary-password'},
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: 'Enter'}));
      await Promise.resolve();
    });

    expect(api.bypassMaintenance).toHaveBeenCalledWith('temporary-password');
    expect(screen.getByText('application content')).toBeInTheDocument();
    expect(sessionStorage.getItem('maintenance-bypass')).toBe('true');
  });

  it('keeps maintenance visible after a rejected bypass', async () => {
    api.checkHealth.mockResolvedValue(unhealthy);
    api.bypassMaintenance.mockResolvedValue({success: false});
    render(
      <HealthCheckProvider>
        <div>application content</div>
      </HealthCheckProvider>,
    );
    await runInitialCheck();

    fireEvent.click(screen.getByRole('button', {name: 'Bypass with Password'}));
    fireEvent.change(screen.getByPlaceholderText('Enter bypass password'), {
      target: {value: 'wrong-password'},
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: 'Enter'}));
      await Promise.resolve();
    });

    expect(screen.getByText('Incorrect password.')).toBeInTheDocument();
    expect(screen.getByText('Service Unavailable')).toBeInTheDocument();
    expect(sessionStorage.getItem('maintenance-bypass')).toBeNull();
  });

  it('polls while unhealthy and clears the timeout on unmount', async () => {
    api.checkHealth.mockResolvedValue(unhealthy);
    const clearTimeoutSpy = vi.spyOn(window, 'clearTimeout');
    const {unmount} = render(
      <HealthCheckProvider pollingInterval={5000}>
        <div>application content</div>
      </HealthCheckProvider>,
    );
    await runInitialCheck();

    const callsAfterInitialization = api.checkHealth.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(api.checkHealth.mock.calls.length).toBeGreaterThan(
      callsAfterInitialization,
    );

    unmount();
    expect(clearTimeoutSpy).toHaveBeenCalled();
  });

  it.each(['timeout', 'offline'])('keeps content visible for a %s failure', async () => {
    api.checkHealth.mockResolvedValue({
      status: 'degraded',
      isHealthy: false,
      maintenance: false,
      maintenanceMessage: '',
    });
    render(
      <HealthCheckProvider>
        <div>application content</div>
      </HealthCheckProvider>,
    );

    await runInitialCheck();

    expect(screen.getByText('application content')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('temporarily unavailable');
    expect(screen.queryByText('Service Unavailable')).not.toBeInTheDocument();
  });

  it('recovers without reloading the page', async () => {
    api.checkHealth
      .mockResolvedValueOnce({
        status: 'degraded',
        isHealthy: false,
        maintenance: false,
        maintenanceMessage: '',
      })
      .mockResolvedValueOnce(healthy);
    render(
      <HealthCheckProvider pollingInterval={5000}>
        <div>application content</div>
      </HealthCheckProvider>,
    );
    await runInitialCheck();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByText('application content')).toBeInTheDocument();
  });

  it('cleans up a delayed initial check before it runs', () => {
    const clearTimeoutSpy = vi.spyOn(window, 'clearTimeout');
    const {unmount} = render(
      <HealthCheckProvider initialDelay={5000}>
        <div>application content</div>
      </HealthCheckProvider>,
    );

    unmount();

    expect(clearTimeoutSpy).toHaveBeenCalled();
    expect(api.checkHealth).not.toHaveBeenCalled();
  });
});
