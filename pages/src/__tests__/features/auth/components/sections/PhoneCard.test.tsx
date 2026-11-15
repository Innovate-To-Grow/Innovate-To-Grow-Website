import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import type {ContactPhone} from '@/features/auth/api';
import {PhoneCard, UNVERIFIED_PHONE_NOTE} from '@/features/auth/components/sections/PhoneCard';

const phone = (overrides: Partial<ContactPhone> = {}): ContactPhone => ({
  id: 'p-1',
  phone_number: '2095551234',
  region: '1-US',
  region_display: 'United States (+1)',
  subscribe: false,
  verified: true,
  created_at: '2026-01-02T00:00:00Z',
  ...overrides,
});

const baseProps = (overrides: Record<string, unknown> = {}) => ({
  phone: phone(),
  verifyingId: null,
  verifyCode: '',
  verifyLoading: false,
  verifyError: null,
  resendLoading: false,
  onToggleSubscribe: vi.fn(),
  onToggleVerify: vi.fn(),
  onVerifyCodeChange: vi.fn(),
  onVerifySubmit: vi.fn(),
  onResend: vi.fn(),
  onCancelVerify: vi.fn(),
  onDelete: vi.fn(),
  ...overrides,
});

describe('PhoneCard', () => {
  afterEach(cleanup);

  it('shows a verified number without the sign-in note or a Verify button', () => {
    render(<PhoneCard {...baseProps()} />);

    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.queryByText(UNVERIFIED_PHONE_NOTE)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Verify'})).not.toBeInTheDocument();
  });

  it('tells the member an unverified number cannot sign in yet, next to its Verify button', () => {
    const onToggleVerify = vi.fn();
    render(<PhoneCard {...baseProps({phone: phone({verified: false}), onToggleVerify})} />);

    expect(screen.getByText('Unverified')).toBeInTheDocument();
    expect(screen.getByText(UNVERIFIED_PHONE_NOTE)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Verify'}));
    expect(onToggleVerify).toHaveBeenCalledWith('p-1');
  });
});
