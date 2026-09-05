import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {DeleteAccountSection} from '@/features/auth/components/pages/account/DeleteAccountSection';

const renderSection = (overrides: Record<string, unknown> = {}) => {
  const props = {
    deleteCodeRequested: false,
    deleteCode: '',
    deleteVerificationToken: null,
    deleteLoading: false,
    deleteMessage: null,
    deleteError: null,
    onDeleteRequestCode: vi.fn(),
    onDeleteVerifyCode: vi.fn(),
    onDeleteConfirm: vi.fn(),
    onDeleteCodeChange: vi.fn(),
    ...overrides,
  };
  render(<DeleteAccountSection {...props} />);
  return props;
};

const toggle = () => screen.getByRole('heading', {name: 'Delete Account'}).closest('button')!;

describe('DeleteAccountSection', () => {
  afterEach(cleanup);

  it('is collapsed by default and expands on click', () => {
    renderSection();

    expect(screen.queryByText(/permanently deletes/)).not.toBeInTheDocument();
    fireEvent.click(toggle());
    expect(screen.getByText(/permanently deletes/)).toBeInTheDocument();
  });

  it('collapses when toggled again', () => {
    renderSection();

    fireEvent.click(toggle());
    expect(screen.getByText(/permanently deletes/)).toBeInTheDocument();
    fireEvent.click(toggle());
    expect(screen.queryByText(/permanently deletes/)).not.toBeInTheDocument();
  });

  it('requests a deletion code', () => {
    const props = renderSection();

    fireEvent.click(toggle());
    fireEvent.click(screen.getByRole('button', {name: 'Send Deletion Code'}));
    expect(props.onDeleteRequestCode).toHaveBeenCalled();
  });

  it('renders success and error alerts', () => {
    renderSection({deleteMessage: 'Code sent', deleteError: 'Bad code'});

    fireEvent.click(toggle());
    expect(screen.getByRole('status')).toHaveTextContent('Code sent');
    expect(screen.getByRole('alert')).toHaveTextContent('Bad code');
  });

  it('forwards the deletion code entry', () => {
    const props = renderSection({deleteCodeRequested: true, deleteCode: ''});

    fireEvent.click(toggle());
    fireEvent.change(screen.getByLabelText('6-digit verification code'), {target: {value: '123456'}});
    expect(props.onDeleteCodeChange).toHaveBeenCalledWith('123456');
  });

  it('submits the deletion verification code', () => {
    const props = renderSection({deleteCodeRequested: true, deleteCode: '123456'});

    fireEvent.click(toggle());
    fireEvent.submit(screen.getByRole('button', {name: 'Verify Code'}).closest('form')!);
    expect(props.onDeleteVerifyCode).toHaveBeenCalled();
  });

  it('disables Verify Code until six digits are entered', () => {
    renderSection({deleteCodeRequested: true, deleteCode: '12'});

    fireEvent.click(toggle());
    expect(screen.getByRole('button', {name: 'Verify Code'})).toBeDisabled();
  });

  it('confirms the deletion once verified', () => {
    const props = renderSection({deleteVerificationToken: 'tok'});

    fireEvent.click(toggle());
    expect(screen.getByText(/Your code has been verified/)).toBeInTheDocument();

    const form = screen.getByText(/Your code has been verified/).closest('form')!;
    fireEvent.submit(form);
    expect(props.onDeleteConfirm).toHaveBeenCalled();
  });

  it('renders the Delete Account confirmation button', () => {
    renderSection({deleteVerificationToken: 'tok'});

    fireEvent.click(toggle());
    const form = screen.getByText(/Your code has been verified/).closest('form')!;
    expect(within(form).getByRole('button', {name: 'Delete Account'})).toBeInTheDocument();
  });

  it('shows the sending label while the code request is loading', () => {
    renderSection({deleteLoading: true});

    fireEvent.click(toggle());
    expect(screen.getByText('Sending...')).toBeInTheDocument();
  });

  it('shows the verifying label while the code is being verified', () => {
    renderSection({deleteCodeRequested: true, deleteCode: '123456', deleteLoading: true});

    fireEvent.click(toggle());
    expect(screen.getByText('Verifying...')).toBeInTheDocument();
  });

  it('shows the deleting label while the account is being deleted', () => {
    renderSection({deleteVerificationToken: 'tok', deleteLoading: true});

    fireEvent.click(toggle());
    expect(screen.getByText('Deleting...')).toBeInTheDocument();
  });
});
