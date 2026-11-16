import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import type {ContactEmail} from '@/features/auth/api';
import {ContactEmailCard} from '@/features/auth/components/sections/email/ContactEmailCard';

const contact = (overrides: Partial<ContactEmail> = {}): ContactEmail => ({
  id: 'e-1',
  email_address: 'secondary@example.com',
  email_type: 'secondary',
  subscribe: true,
  verified: true,
  created_at: '2026-01-02T00:00:00Z',
  ...overrides,
});

const baseProps = (overrides: Record<string, unknown> = {}) => ({
  contact: contact(),
  verifyingId: null,
  verifyCode: '',
  verifyLoading: false,
  verifyError: null,
  resendLoading: false,
  onContactTypeChange: vi.fn(),
  onContactSubscribeToggle: vi.fn(),
  onToggleVerify: vi.fn(),
  onVerifyCodeChange: vi.fn(),
  onVerifySubmit: vi.fn(),
  onResend: vi.fn(),
  onDelete: vi.fn(),
  onCancelVerify: vi.fn(),
  onMakePrimary: vi.fn(),
  makePrimaryLoadingId: null,
  secondaryDisabled: false,
  ...overrides,
});

describe('ContactEmailCard', () => {
  afterEach(cleanup);

  it('disables the role select while that contact is being made primary', () => {
    render(<ContactEmailCard {...baseProps({makePrimaryLoadingId: 'e-1'})} />);

    expect(screen.getByRole('combobox', {name: 'Role'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Updating...'})).toBeDisabled();
  });

  it('does not disable the role select for a different contact', () => {
    render(<ContactEmailCard {...baseProps({makePrimaryLoadingId: 'e-2'})} />);

    expect(screen.getByRole('combobox', {name: 'Role'})).not.toBeDisabled();
  });

  it('renders the resending state on the resend button', () => {
    render(
      <ContactEmailCard
        {...baseProps({
          contact: contact({verified: false}),
          verifyingId: 'e-1',
          resendLoading: true,
        })}
      />,
    );

    expect(screen.getByRole('button', {name: 'Sending...'})).toBeInTheDocument();
  });

  it('renders the submitting state on the submit button', () => {
    render(
      <ContactEmailCard
        {...baseProps({
          contact: contact({verified: false}),
          verifyingId: 'e-1',
          verifyLoading: true,
          verifyCode: '123456',
        })}
      />,
    );

    expect(screen.getByRole('button', {name: 'Submitting...'})).toBeInTheDocument();
  });

  it('passes the code change handler through to the input', () => {
    const onVerifyCodeChange = vi.fn();
    render(
      <ContactEmailCard
        {...baseProps({
          contact: contact({verified: false}),
          verifyingId: 'e-1',
          onVerifyCodeChange,
        })}
      />,
    );

    fireEvent.change(screen.getByLabelText('6-digit verification code'), {
      target: {value: '123456'},
    });

    expect(onVerifyCodeChange).toHaveBeenCalledWith('123456');
  });

  it('keeps the Secondary option enabled for the existing secondary contact', () => {
    render(
      <ContactEmailCard
        {...baseProps({contact: contact({email_type: 'secondary'}), secondaryDisabled: true})}
      />,
    );

    expect(screen.getByRole('option', {name: 'Secondary'})).not.toBeDisabled();
  });
});
