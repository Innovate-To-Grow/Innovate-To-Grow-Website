import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ErrorBoundary} from '@/app/ErrorBoundary/ErrorBoundary';

const originalLocation = window.location;

function Throws(): never {
  throw new Error('boom');
}

function Healthy() {
  return <div>all good</div>;
}

function stubLocationReload() {
  const reload = vi.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {reload},
  });
  return reload;
}

describe('ErrorBoundary', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });

  it('renders children when nothing throws', () => {
    render(
      <ErrorBoundary>
        <Healthy />
      </ErrorBoundary>,
    );

    expect(screen.getByText('all good')).toBeInTheDocument();
  });

  it('renders the fallback UI and reloads on refresh', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const reload = stubLocationReload();

    render(
      <ErrorBoundary>
        <Throws />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Refresh'}));
    expect(reload).toHaveBeenCalledOnce();
  });
});
