import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {HealthCheckContext, useHealthCheck} from '@/app/MaintenanceMode/context';

function Probe() {
  const {status, isHealthy, isLoading} = useHealthCheck();
  return <div>{`${status}:${isHealthy}:${isLoading}`}</div>;
}

describe('HealthCheckContext', () => {
  afterEach(() => {
    cleanup();
  });

  it('provides sensible defaults', () => {
    render(<Probe />);

    expect(screen.getByText('healthy:true:true')).toBeInTheDocument();
  });

  it('allows overriding via a custom provider', () => {
    render(
      <HealthCheckContext.Provider
        value={{
          status: 'maintenance',
          isHealthy: false,
          isLoading: false,
          maintenance: true,
          maintenanceMessage: 'down',
          checkNow: async () => {},
        }}
      >
        <Probe />
      </HealthCheckContext.Provider>,
    );

    expect(screen.getByText('maintenance:false:false')).toBeInTheDocument();
  });
});
