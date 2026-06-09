import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

import {ContactEmailCard} from '@/features/auth/components/sections/ContactEmailCard';
import {EmailAddForm} from '@/features/auth/components/sections/EmailAddForm';
import type {ContactEmail} from '@/features/auth/api';

const contact: ContactEmail = {
  id: 'email-1',
  email_address: 'secondary@example.com',
  email_type: 'other',
  verified: false,
  subscribe: true,
  created_at: '',
  updated_at: '',
};

describe('email section components', () => {
  it('renders contact email controls and inline verification', () => {
    const onType = vi.fn();
    const onSubscribe = vi.fn();
    const onVerify = vi.fn((event) => event.preventDefault());
    const onResend = vi.fn();
    const onDelete = vi.fn();
    const onMakePrimary = vi.fn();

    render(
      <ContactEmailCard
        contact={contact}
        verifyingId="email-1"
        verifyCode="123456"
        verifyLoading={false}
        verifyError="Bad code"
        resendLoading={false}
        onContactTypeChange={onType}
        onContactSubscribeToggle={onSubscribe}
        onToggleVerify={vi.fn()}
        onVerifyCodeChange={vi.fn()}
        onVerifySubmit={onVerify}
        onResend={onResend}
        onDelete={onDelete}
        onCancelVerify={vi.fn()}
        onMakePrimary={onMakePrimary}
        makePrimaryLoadingId={null}
        secondaryDisabled={false}
      />,
    );

    fireEvent.change(screen.getByLabelText('Email role'), {target: {value: 'secondary'}});
    expect(onType).toHaveBeenCalledWith(contact, 'secondary');
    fireEvent.click(screen.getAllByLabelText('Newsletters')[0]);
    expect(onSubscribe).toHaveBeenCalledWith(contact);
    fireEvent.submit(screen.getByRole('button', {name: 'Submit code'}).closest('form')!);
    expect(onVerify).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Resend Code'}));
    expect(onResend).toHaveBeenCalledWith('email-1');
    fireEvent.click(screen.getByRole('button', {name: 'Remove'}));
    expect(onDelete).toHaveBeenCalledWith('email-1');
    expect(screen.getByText('Bad code')).toBeInTheDocument();
  });

  it('routes verified contact promotion through make primary', () => {
    const onMakePrimary = vi.fn();

    render(
      <ContactEmailCard
        contact={{...contact, verified: true}}
        verifyingId={null}
        verifyCode=""
        verifyLoading={false}
        verifyError={null}
        resendLoading={false}
        onContactTypeChange={vi.fn()}
        onContactSubscribeToggle={vi.fn()}
        onToggleVerify={vi.fn()}
        onVerifyCodeChange={vi.fn()}
        onVerifySubmit={vi.fn()}
        onResend={vi.fn()}
        onDelete={vi.fn()}
        onCancelVerify={vi.fn()}
        onMakePrimary={onMakePrimary}
        makePrimaryLoadingId={null}
        secondaryDisabled={false}
      />,
    );

    fireEvent.change(screen.getByLabelText('Email role'), {target: {value: 'primary'}});
    expect(onMakePrimary).toHaveBeenCalledWith('email-1');
  });

  it('renders and submits add-email form controls', () => {
    const onSubmit = vi.fn((event) => event.preventDefault());
    const onEmailChange = vi.fn();
    const onTypeChange = vi.fn();
    const onSubscribeChange = vi.fn();
    const onCancel = vi.fn();

    render(
      <EmailAddForm
        addEmail="new@example.com"
        addType="secondary"
        addSubscribe={false}
        addLoading={false}
        addError="Email exists"
        secondaryDisabled
        onEmailChange={onEmailChange}
        onTypeChange={onTypeChange}
        onSubscribeChange={onSubscribeChange}
        onSubmit={onSubmit}
        onCancel={onCancel}
      />,
    );

    expect(screen.getByText('Email exists')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Email Address'), {target: {value: 'other@example.com'}});
    expect(onEmailChange).toHaveBeenCalledWith('other@example.com');
    fireEvent.change(screen.getByLabelText('Type'), {target: {value: 'other'}});
    expect(onTypeChange).toHaveBeenCalledWith('other');
    fireEvent.click(screen.getByLabelText('Newsletters'));
    expect(onSubscribeChange).toHaveBeenCalledWith(true);
    fireEvent.submit(screen.getByRole('button', {name: 'Add & Send Verification'}).closest('form')!);
    expect(onSubmit).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
