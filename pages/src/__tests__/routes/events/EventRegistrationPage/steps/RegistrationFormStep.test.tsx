import {cleanup, fireEvent, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import type {EventRegistrationOptions} from '@/features/events/api';
import {type RegistrationFormStepProps, renderForm, submitForm} from '@/__tests__/routes/events/EventRegistrationPage/steps/registrationFormStepFixtures';

describe('RegistrationFormStep', () => {
  afterEach(() => {
    cleanup();
  });

  it('blocks submission and shows a last-name error when last name is blank', () => {
    const {onSubmit} = renderForm({}, {attendeeLastName: ''});

    submitForm();

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Last name is required.')).toBeInTheDocument();
  });

  it('does not prompt for a phone number when phone collection is off', () => {
    const {onSubmit} = renderForm({collect_phone: false, verify_phone: false});

    expect(screen.queryByLabelText(/Phone Number/)).not.toBeInTheDocument();
    submitForm();
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('prompts for an optional phone number without requiring verification', () => {
    const {onSubmit} = renderForm({collect_phone: true, verify_phone: false});

    expect(screen.getByLabelText(/Phone Number/)).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Send phone code'})).not.toBeInTheDocument();
    submitForm();
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('requires verification for a supplied phone when verification is enabled', () => {
    const {onSubmit} = renderForm({collect_phone: true, verify_phone: true}, {attendeePhone: '2025550123'});

    expect(screen.getByLabelText(/Phone Number/)).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Send phone code'})).toBeInTheDocument();
    submitForm();
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Phone number must be verified.')).toBeInTheDocument();
  });

  it('does not block on stale verify_phone data when phone collection is off', () => {
    const {onSubmit} = renderForm({collect_phone: false, verify_phone: true});

    expect(screen.queryByLabelText(/Phone Number/)).not.toBeInTheDocument();
    submitForm();
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(screen.queryByText('Phone number must be verified.')).not.toBeInTheDocument();
  });

  describe.each(['phone', 'secondary email'] as const)('%s settings', (contact) => {
    const flags = (collect: boolean, verify: boolean, required: boolean): Partial<EventRegistrationOptions> => contact === 'phone'
      ? {collect_phone: collect, verify_phone: verify, require_phone: required}
      : {allow_secondary_email: collect, verify_secondary_email: verify, require_secondary_email: required};
    const values = (value: string, verified = false): Partial<RegistrationFormStepProps> => contact === 'phone'
      ? {attendeePhone: value, phoneVerified: verified}
      : {attendeeSecondaryEmail: value, secondaryEmailVerified: verified};
    const validValue = contact === 'phone' ? '2025550123' : 'personal@example.com';
    const label = contact === 'phone' ? /Phone Number/ : /Secondary Email/;
    const requiredError = contact === 'phone' ? 'Phone number is required.' : 'Secondary email is required.';
    const verificationError = contact === 'phone' ? 'Phone number must be verified.' : 'Secondary email must be verified.';

    it.each([false, true])('allows a blank optional contact with verification=%s', (verify) => {
      const {onSubmit} = renderForm(flags(true, verify, false));
      expect(screen.getByLabelText(label)).toHaveAttribute('aria-required', 'false');
      submitForm();
      expect(onSubmit).toHaveBeenCalledOnce();
    });

    it.each([false, true])('requires a nonblank contact with verification=%s', (verify) => {
      const {onSubmit} = renderForm(flags(true, verify, true));
      expect(screen.getByLabelText(label)).toHaveAttribute('aria-required', 'true');
      submitForm();
      expect(onSubmit).not.toHaveBeenCalled();
      expect(screen.getByText(requiredError)).toBeInTheDocument();
      expect(screen.queryByText(verificationError)).not.toBeInTheDocument();
    });

    it('accepts a required unverified value when verification is disabled', () => {
      const {onSubmit} = renderForm(flags(true, false, true), values(validValue));
      submitForm();
      expect(onSubmit).toHaveBeenCalledOnce();
    });

    it('blocks an optional supplied value until verified', () => {
      const {onSubmit} = renderForm(flags(true, true, false), values(validValue));
      submitForm();
      expect(onSubmit).not.toHaveBeenCalled();
      expect(screen.getByText(verificationError)).toBeInTheDocument();
    });

    it('accepts a required verified value', () => {
      const {onSubmit} = renderForm(flags(true, true, true), values(validValue, true));
      submitForm();
      expect(onSubmit).toHaveBeenCalledOnce();
      expect(screen.getByText('Verified')).toBeInTheDocument();
    });

    it('ignores dependent settings and stale values when collection is disabled', () => {
      const {onSubmit} = renderForm(flags(false, true, true), values('ada@example.com'));
      expect(screen.queryByLabelText(label)).not.toBeInTheDocument();
      submitForm();
      expect(onSubmit).toHaveBeenCalledOnce();
    });
  });

  it.each([
    ['invalid', 'Enter a valid secondary email address.'],
    [' ADA@EXAMPLE.COM ', 'Secondary email must be different from the primary email.'],
  ])('blocks invalid secondary email %s before sending or submitting', (email, error) => {
    const {onSubmit} = renderForm(
      {allow_secondary_email: true, verify_secondary_email: true},
      {attendeeSecondaryEmail: email},
    );
    expect(screen.getByRole('button', {name: 'Send secondary email code'})).toBeDisabled();
    submitForm();
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(error)).toBeInTheDocument();
  });

  it('keeps phone and secondary email verification controls distinct', () => {
    const onSecondaryEmailCodeChange = vi.fn();
    const onSendSecondaryEmailCode = vi.fn();
    const onVerifySecondaryEmailCode = vi.fn();
    renderForm(
      {allow_secondary_email: true, verify_secondary_email: true, collect_phone: true, verify_phone: true},
      {
        attendeePhone: '2025550123', attendeeSecondaryEmail: 'personal@example.com',
        phoneCodeSent: true, secondaryEmailCodeSent: true, secondaryEmailCode: '123456',
        onSecondaryEmailCodeChange, onSendSecondaryEmailCode, onVerifySecondaryEmailCode,
      },
    );
    fireEvent.change(screen.getByLabelText('Secondary email verification code'), {target: {value: '12x34567'}});
    fireEvent.click(screen.getByRole('button', {name: 'Resend secondary email code'}));
    fireEvent.click(screen.getByRole('button', {name: 'Verify secondary email'}));
    expect(onSecondaryEmailCodeChange).toHaveBeenCalledWith('123456');
    expect(onSendSecondaryEmailCode).toHaveBeenCalledOnce();
    expect(onVerifySecondaryEmailCode).toHaveBeenCalledOnce();
    expect(screen.getByLabelText('Phone verification code')).toBeInTheDocument();
  });

  it('requires answers to required questions', () => {
    const {onSubmit} = renderForm({
      questions: [{id: 'q1', text: 'Dietary restrictions?', is_required: true, order: 0}],
    });

    submitForm();

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('This field is required.')).toBeInTheDocument();
  });

  it('renders sorted questions and forwards answer changes', () => {
    const onAnswerChange = vi.fn();
    renderForm(
      {
        questions: [
          {id: 'q2', text: 'Second?', is_required: false, order: 2},
          {id: 'q1', text: 'First?', is_required: true, order: 1},
        ],
      },
      {onAnswerChange},
    );

    fireEvent.change(screen.getByLabelText(/First\?/), {target: {value: 'Answer 1'}});

    expect(onAnswerChange).toHaveBeenCalledWith('q1', 'Answer 1');
  });
});
