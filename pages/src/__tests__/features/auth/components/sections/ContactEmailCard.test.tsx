import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import type {ContactEmail} from '@/features/auth/api';
import {ContactEmailCard} from '@/features/auth/components/sections/ContactEmailCard';

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

  it('renders a verified contact with a Primary role option', () => {
    render(<ContactEmailCard {...baseProps()} />);

    expect(screen.getByText('secondary@example.com')).toBeInTheDocument();
    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.getByRole('combobox', {name: 'Email role'})).toHaveValue('secondary');
    expect(screen.getByRole('option', {name: 'Primary'})).toBeInTheDocument();
  });

  it('renders an unverified contact without a Primary role option', () => {
    render(<ContactEmailCard {...baseProps({contact: contact({verified: false})})} />);

    expect(screen.getByText('Unverified')).toBeInTheDocument();
    expect(screen.queryByRole('option', {name: 'Primary'})).not.toBeInTheDocument();
  });

  it('calls onMakePrimary when the Primary option is selected', () => {
    const onMakePrimary = vi.fn();
    render(<ContactEmailCard {...baseProps({onMakePrimary})} />);

    fireEvent.change(screen.getByRole('combobox', {name: 'Email role'}), {
      target: {value: 'primary'},
    });

    expect(onMakePrimary).toHaveBeenCalledWith('e-1');
  });

  it('calls onContactTypeChange for a non-primary role selection', () => {
    const onContactTypeChange = vi.fn();
    render(<ContactEmailCard {...baseProps({onContactTypeChange})} />);

    fireEvent.change(screen.getByRole('combobox', {name: 'Email role'}), {
      target: {value: 'other'},
    });

    expect(onContactTypeChange).toHaveBeenCalledWith(contact(), 'other');
  });

  it('calls onContactSubscribeToggle when the newsletter checkbox changes', () => {
    const onContactSubscribeToggle = vi.fn();
    render(<ContactEmailCard {...baseProps({onContactSubscribeToggle})} />);

    fireEvent.click(screen.getByRole('checkbox', {name: 'Newsletters'}));

    expect(onContactSubscribeToggle).toHaveBeenCalledWith(contact());
  });

  it('shows a Verify button for an unverified contact and triggers verification', () => {
    const onToggleVerify = vi.fn();
    render(<ContactEmailCard {...baseProps({contact: contact({verified: false}), onToggleVerify})} />);

    fireEvent.click(screen.getByRole('button', {name: 'Verify'}));

    expect(onToggleVerify).toHaveBeenCalledWith('e-1');
  });

  it('hides the Verify button while the contact is being verified', () => {
    render(
      <ContactEmailCard
        {...baseProps({contact: contact({verified: false}), verifyingId: 'e-1'})}
      />,
    );

    expect(screen.queryByRole('button', {name: 'Verify'})).not.toBeInTheDocument();
    expect(screen.getByLabelText('6-digit verification code')).toBeInTheDocument();
  });

  it('calls onDelete when Remove is clicked', () => {
    const onDelete = vi.fn();
    render(<ContactEmailCard {...baseProps({onDelete})} />);

    fireEvent.click(screen.getByRole('button', {name: 'Remove'}));

    expect(onDelete).toHaveBeenCalledWith('e-1');
  });

  it('disables the submit button until the code is complete', () => {
    render(
      <ContactEmailCard
        {...baseProps({contact: contact({verified: false}), verifyingId: 'e-1'})}
      />,
    );

    expect(screen.getByRole('button', {name: 'Submit code'})).toBeDisabled();
  });

  it('submits the verification form', () => {
    const onVerifySubmit = vi.fn();
    render(
      <ContactEmailCard
        {...baseProps({
          contact: contact({verified: false}),
          verifyingId: 'e-1',
          verifyCode: '123456',
          onVerifySubmit,
        })}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Submit code'}));

    expect(onVerifySubmit).toHaveBeenCalled();
  });

  it('resends and cancels from the inline verification form', () => {
    const onResend = vi.fn();
    const onCancelVerify = vi.fn();
    render(
      <ContactEmailCard
        {...baseProps({
          contact: contact({verified: false}),
          verifyingId: 'e-1',
          onResend,
          onCancelVerify,
        })}
      />,
    );

    fireEvent.click(screen.getByRole('button', {name: 'Resend Code'}));
    expect(onResend).toHaveBeenCalledWith('e-1');

    fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
    expect(onCancelVerify).toHaveBeenCalled();
  });

  it('renders a verify error inside the inline form', () => {
    render(
      <ContactEmailCard
        {...baseProps({
          contact: contact({verified: false}),
          verifyingId: 'e-1',
          verifyError: 'Bad code',
        })}
      />,
    );

    expect(screen.getByText('Bad code')).toBeInTheDocument();
  });

  it('disables the secondary option when another address is already secondary', () => {
    render(
      <ContactEmailCard
        {...baseProps({contact: contact({email_type: 'other'}), secondaryDisabled: true})}
      />,
    );

    expect(screen.getByRole('option', {name: 'Secondary'})).toBeDisabled();
    expect(screen.getByRole('option', {name: 'Secondary'})).toHaveAttribute(
      'title',
      'Another address is already set as secondary.',
    );
  });

  it('disables the role select while that contact is being made primary', () => {
    render(<ContactEmailCard {...baseProps({makePrimaryLoadingId: 'e-1'})} />);

    expect(screen.getByRole('combobox', {name: 'Email role'})).toBeDisabled();
  });

  it('does not disable the role select for a different contact', () => {
    render(<ContactEmailCard {...baseProps({makePrimaryLoadingId: 'e-2'})} />);

    expect(screen.getByRole('combobox', {name: 'Email role'})).not.toBeDisabled();
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
