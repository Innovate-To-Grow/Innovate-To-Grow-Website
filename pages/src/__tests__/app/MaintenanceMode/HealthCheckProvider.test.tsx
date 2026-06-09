import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {HealthCheckProvider} from '@/app/MaintenanceMode/HealthCheckProvider';
import {useHealthCheck} from '@/app/MaintenanceMode/context';

const healthMocks = vi.hoisted(() => ({
  bypassMaintenance: vi.fn(),
  checkHealth: vi.fn(),
}));

vi.mock('@/lib/health', () => healthMocks);

const HealthConsumer = () => {
  const health = useHealthCheck();
  return (
    <div>
      <span data-testid="healthy">{String(health.isHealthy)}</span>
      <button type="button" onClick={() => void health.checkNow()}>
        Check now
      </button>
    </div>
  );
};

describe('HealthCheckProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    healthMocks.checkHealth.mockResolvedValue({
      isHealthy: true,
      maintenance: false,
      maintenanceMessage: '',
    });
    healthMocks.bypassMaintenance.mockResolvedValue({success: true});
  });

  it('renders children while the backend is healthy and exposes health context', async () => {
    render(
      <HealthCheckProvider>
        <HealthConsumer />
      </HealthCheckProvider>,
    );

    expect(screen.getByTestId('healthy')).toHaveTextContent('true');
    await waitFor(() => expect(healthMocks.checkHealth).toHaveBeenCalled());
    const callsBeforeManualCheck = healthMocks.checkHealth.mock.calls.length;

    fireEvent.click(screen.getByRole('button', {name: 'Check now'}));
    await waitFor(() => expect(healthMocks.checkHealth.mock.calls.length).toBeGreaterThan(callsBeforeManualCheck));
  });

  it('renders maintenance mode after an unhealthy health check and allows bypass', async () => {
    healthMocks.checkHealth.mockResolvedValue({
      isHealthy: false,
      maintenance: true,
      maintenanceMessage: 'Admin maintenance window.',
    });

    render(
      <HealthCheckProvider pollingInterval={1000}>
        <div>Application shell</div>
      </HealthCheckProvider>,
    );

    expect(await screen.findByText('Admin maintenance window.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Bypass with Password'}));
    fireEvent.change(screen.getByPlaceholderText('Enter bypass password'), {
      target: {value: 'let-me-in'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Enter'}));

    await waitFor(() => expect(healthMocks.bypassMaintenance).toHaveBeenCalledWith('let-me-in'));
    expect(await screen.findByText('Application shell')).toBeInTheDocument();
    expect(sessionStorage.getItem('maintenance-bypass')).toBe('true');
  });
});
