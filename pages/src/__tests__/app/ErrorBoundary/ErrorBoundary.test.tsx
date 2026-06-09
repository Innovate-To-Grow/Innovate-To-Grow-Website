import {fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ErrorBoundary} from '@/app/ErrorBoundary/ErrorBoundary';

const Bomb = () => {
  throw new Error('render failed');
};

describe('ErrorBoundary', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders children until a child throws, then shows the fallback UI', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const {rerender} = render(
      <ErrorBoundary>
        <div>Ready</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText('Ready')).toBeInTheDocument();

    rerender(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('Please refresh the page or try again later.')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Refresh'})).toBeInTheDocument();
    expect(errorSpy).toHaveBeenCalled();
  });

  it('wires the refresh button to the browser reload function', () => {
    const reload = vi.fn();
    const originalLocation = window.location;
    vi.spyOn(console, 'error').mockImplementation(() => {});
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {...originalLocation, reload},
    });

    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Refresh'}));
    expect(reload).toHaveBeenCalledTimes(1);

    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });
});
