import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

import type {ContactPhone} from '@/features/auth/api';
import {PhoneAddForm} from '@/features/auth/components/sections/PhoneAddForm';
import {PhoneCard} from '@/features/auth/components/sections/PhoneCard';
import {PhonePendingVerifyPanel} from '@/features/auth/components/sections/PhonePendingVerifyPanel';

const phone: ContactPhone = {
  id: 'phone-1',
  phone_number: '+15551234567',
  region: '1-US',
  region_display: 'United States',
  subscribe: true,
  verified: false,
  created_at: '',
};

describe('phone section components', () => {
  it('renders and submits add-phone form controls', () => {
    const onSubmit = vi.fn((event) => event.preventDefault());
    const onRegionChange = vi.fn();
    const onPhoneNumberChange = vi.fn();
    const onSubscribeChange = vi.fn();
    const onCancel = vi.fn();

    render(
      <PhoneAddForm
        addRegion="1-US"
        addPhoneNumber="5551234567"
        addSubscribe={false}
        addLoading={false}
        addError="Phone exists"
        onRegionChange={onRegionChange}
        onPhoneNumberChange={onPhoneNumberChange}
        onSubscribeChange={onSubscribeChange}
        onSubmit={onSubmit}
        onCancel={onCancel}
      />,
    );

    expect(screen.getByText('Phone exists')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Region'), {target: {value: '44'}});
    expect(onRegionChange).toHaveBeenCalledWith('44');
    fireEvent.change(screen.getByLabelText('Phone Number'), {target: {value: '(555) 222-3333'}});
    expect(onPhoneNumberChange).toHaveBeenCalledWith('5552223333');
    fireEvent.click(screen.getAllByLabelText('Allow SMS Message')[0]);
    expect(onSubscribeChange).toHaveBeenCalledWith(true);
    fireEvent.submit(screen.getByRole('button', {name: 'Add Phone'}).closest('form')!);
    expect(onSubmit).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('renders phone card actions and inline verification', () => {
    const onToggleSubscribe = vi.fn();
    const onVerifySubmit = vi.fn((event) => event.preventDefault());
    const onResend = vi.fn();
    const onDelete = vi.fn();
    const onCancelVerify = vi.fn();
    const onVerifyCodeChange = vi.fn();

    render(
      <PhoneCard
        phone={phone}
        verifyingId="phone-1"
        verifyCode="123456"
        verifyLoading={false}
        verifyError="Bad code"
        resendLoading={false}
        onToggleSubscribe={onToggleSubscribe}
        onToggleVerify={vi.fn()}
        onVerifyCodeChange={onVerifyCodeChange}
        onVerifySubmit={onVerifySubmit}
        onResend={onResend}
        onCancelVerify={onCancelVerify}
        onDelete={onDelete}
      />,
    );

    expect(screen.getByText('(555)123-4567')).toBeInTheDocument();
    expect(screen.getByText('Bad code')).toBeInTheDocument();
    fireEvent.click(screen.getAllByLabelText('Allow SMS Message')[0]);
    expect(onToggleSubscribe).toHaveBeenCalledWith(phone);
    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '654321'}});
    expect(onVerifyCodeChange).toHaveBeenCalledWith('654321');
    fireEvent.submit(screen.getByRole('button', {name: 'Submit code'}).closest('form')!);
    expect(onVerifySubmit).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', {name: 'Resend Code'}));
    expect(onResend).toHaveBeenCalledWith('phone-1');
    fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
    expect(onCancelVerify).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', {name: 'Remove'}));
    expect(onDelete).toHaveBeenCalledWith('phone-1');
  });

  it('renders verified phone cards without verification controls', () => {
    const onToggleVerify = vi.fn();

    render(
      <PhoneCard
        phone={{...phone, verified: true}}
        verifyingId={null}
        verifyCode=""
        verifyLoading={false}
        verifyError={null}
        resendLoading={false}
        onToggleSubscribe={vi.fn()}
        onToggleVerify={onToggleVerify}
        onVerifyCodeChange={vi.fn()}
        onVerifySubmit={vi.fn()}
        onResend={vi.fn()}
        onCancelVerify={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Verify'})).toBeNull();
    expect(onToggleVerify).not.toHaveBeenCalled();
  });

  it('renders pending phone verification controls', () => {
    const onSubmit = vi.fn((event) => event.preventDefault());
    const onCodeChange = vi.fn();
    const onResend = vi.fn();
    const onAbandon = vi.fn();

    render(
      <PhonePendingVerifyPanel
        phone={phone}
        verifyCode="123456"
        verifyLoading={false}
        verifyError="Wrong SMS code"
        resendLoading={false}
        abandonLoading={false}
        onVerifyCodeChange={onCodeChange}
        onVerifySubmit={onSubmit}
        onResend={onResend}
        onAbandon={onAbandon}
      />,
    );

    expect(screen.getByText('Wrong SMS code')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', {name: '6-digit verification code'}), {target: {value: '111222'}});
    expect(onCodeChange).toHaveBeenCalledWith('111222');
    fireEvent.submit(screen.getByRole('button', {name: 'Submit code'}).closest('form')!);
    expect(onSubmit).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', {name: 'Resend Code'}));
    expect(onResend).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', {name: 'Discard number'}));
    expect(onAbandon).toHaveBeenCalledTimes(1);
  });
});
