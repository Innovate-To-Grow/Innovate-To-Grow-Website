import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {PasswordSection} from '@/features/auth/components/pages/account/PasswordSection';

const renderSection = (overrides: Record<string, unknown> = {}) => {
  const props = {
    passwordCodeRequested: false,
    passwordCode: '',
    passwordVerificationToken: null,
    newPassword: '',
    confirmPassword: '',
    passwordLoading: false,
    passwordMessage: null,
    passwordError: null,
    onPasswordRequestCode: vi.fn(),
    onPasswordVerifyCode: vi.fn(),
    onPasswordConfirm: vi.fn(),
    onPasswordCodeChange: vi.fn(),
    onNewPasswordChange: vi.fn(),
    onConfirmPasswordChange: vi.fn(),
    ...overrides,
  };
  render(<PasswordSection {...props} />);
  return props;
};

describe('PasswordSection', () => {
  afterEach(cleanup);

  it('requests a code from the initial state', () => {
    const props = renderSection();

    fireEvent.click(screen.getByRole('button', {name: 'Send Code'}));
    expect(props.onPasswordRequestCode).toHaveBeenCalled();
  });

  it('renders success and error alerts', () => {
    renderSection({passwordMessage: 'Code sent', passwordError: 'Bad code'});

    expect(screen.getByRole('status')).toHaveTextContent('Code sent');
    expect(screen.getByRole('alert')).toHaveTextContent('Bad code');
  });

  it('sanitizes and forwards the verification code entry', () => {
    const props = renderSection({passwordCodeRequested: true});

    fireEvent.change(screen.getByLabelText('6-digit verification code'), {target: {value: '12a3456'}});
    expect(props.onPasswordCodeChange).toHaveBeenCalledWith('123456');
  });

  it('disables Verify Code until six digits are entered', () => {
    renderSection({passwordCodeRequested: true, passwordCode: '123'});

    expect(screen.getByRole('button', {name: 'Verify Code'})).toBeDisabled();
  });

  it('submits the verification code', () => {
    const props = renderSection({passwordCodeRequested: true, passwordCode: '123456'});

    fireEvent.submit(screen.getByRole('button', {name: 'Verify Code'}).closest('form')!);
    expect(props.onPasswordVerifyCode).toHaveBeenCalled();
  });

  it('forwards the new and confirm password entries', () => {
    const props = renderSection({passwordVerificationToken: 'tok', newPassword: '', confirmPassword: ''});

    fireEvent.change(screen.getByLabelText('New Password'), {target: {value: 'newpass'}});
    fireEvent.change(screen.getByLabelText('Confirm Password'), {target: {value: 'newpass'}});
    expect(props.onNewPasswordChange).toHaveBeenCalledWith('newpass');
    expect(props.onConfirmPasswordChange).toHaveBeenCalledWith('newpass');
  });

  it('submits the new password', () => {
    const props = renderSection({passwordVerificationToken: 'tok', newPassword: 'newpass', confirmPassword: 'newpass'});

    fireEvent.submit(screen.getByRole('button', {name: 'Change Password'}).closest('form')!);
    expect(props.onPasswordConfirm).toHaveBeenCalled();
  });

  it('disables Change Password while the new password fields are empty', () => {
    renderSection({passwordVerificationToken: 'tok', newPassword: '', confirmPassword: ''});

    expect(screen.getByRole('button', {name: 'Change Password'})).toBeDisabled();
  });

  it('shows the sending label while the code request is loading', () => {
    renderSection({passwordLoading: true});

    expect(screen.getByText('Sending...')).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Send Code'})).not.toBeInTheDocument();
  });

  it('shows the verifying label while the code is being verified', () => {
    renderSection({passwordCodeRequested: true, passwordCode: '123456', passwordLoading: true});

    expect(screen.getByText('Verifying...')).toBeInTheDocument();
  });

  it('shows the saving label while the new password is being saved', () => {
    renderSection({
      passwordVerificationToken: 'tok',
      newPassword: 'newpass',
      confirmPassword: 'newpass',
      passwordLoading: true,
    });

    expect(screen.getByText('Saving...')).toBeInTheDocument();
  });
});
