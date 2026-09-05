import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {DetailsSection} from '@/features/auth/components/pages/account/DetailsSection';

describe('DetailsSection', () => {
  afterEach(cleanup);

  it('renders both the email and joined date', () => {
    render(<DetailsSection displayEmail="ada@example.com" dateJoined="2026-01-01T00:00:00Z" />);

    expect(screen.getByText('Email')).toBeInTheDocument();
    expect(screen.getByText('ada@example.com')).toBeInTheDocument();
    expect(screen.getByText('Member Since')).toBeInTheDocument();
  });

  it('renders only the email when no joined date is provided', () => {
    render(<DetailsSection displayEmail="ada@example.com" />);

    expect(screen.getByText('Email')).toBeInTheDocument();
    expect(screen.getByText('ada@example.com')).toBeInTheDocument();
    expect(screen.queryByText('Member Since')).not.toBeInTheDocument();
  });

  it('renders only the joined date when no email is provided', () => {
    render(<DetailsSection dateJoined="2026-01-01T00:00:00Z" />);

    expect(screen.queryByText('Email')).not.toBeInTheDocument();
    expect(screen.getByText('Member Since')).toBeInTheDocument();
  });

  it('renders neither row when both are missing', () => {
    const {container} = render(<DetailsSection />);

    expect(screen.queryByText('Email')).not.toBeInTheDocument();
    expect(screen.queryByText('Member Since')).not.toBeInTheDocument();
    expect(container.querySelector('.account-details-rows')).toBeEmptyDOMElement();
  });
});
