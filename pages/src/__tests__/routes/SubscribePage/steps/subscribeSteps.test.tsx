import {act, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {CodeStep} from '@/routes/SubscribePage/steps/CodeStep';
import {ProfileStep} from '@/routes/SubscribePage/steps/ProfileStep';
import {getSubscribeErrorMessage} from '@/routes/SubscribePage/steps/helpers';

describe('SubscribePage step components', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the code step, gates verification, and handles resend cooldown', async () => {
    vi.useFakeTimers();
    const onCodeChange = vi.fn();
    const onSubmit = vi.fn((event) => event.preventDefault());
    const onBack = vi.fn();
    const onResend = vi.fn().mockResolvedValue(undefined);

    render(
      <CodeStep
        email="ada@example.com"
        code="123456"
        authLoading={false}
        onCodeChange={onCodeChange}
        onSubmit={onSubmit}
        onBack={onBack}
        onResend={onResend}
      />,
    );

    expect(screen.getByText(/ada@example.com/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', {name: 'Verification Code'}), {target: {value: '654321'}});
    expect(onCodeChange).toHaveBeenCalledWith('654321');
    fireEvent.submit(screen.getByRole('button', {name: 'Verify Code'}).closest('form')!);
    expect(onSubmit).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', {name: 'Use a different email'}));
    expect(onBack).toHaveBeenCalledTimes(1);

    expect(screen.getByRole('button', {name: /Resend code \(30s\)/})).toBeDisabled();
    for (let index = 0; index < 30; index += 1) {
      await act(async () => {
        vi.advanceTimersByTime(1_000);
        await Promise.resolve();
      });
    }
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: 'Resend code'}));
      await Promise.resolve();
    });
    expect(onResend).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', {name: /Resend code \(30s\)/})).toBeDisabled();
  });

  it('renders loading code-step controls', () => {
    render(
      <CodeStep
        email="ada@example.com"
        code="123456"
        authLoading
        onCodeChange={vi.fn()}
        onSubmit={vi.fn()}
        onBack={vi.fn()}
        onResend={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', {name: /Verifying/})).toBeDisabled();
  });

  it('renders profile step organization controls and field callbacks', () => {
    const onSubmit = vi.fn((event) => event.preventDefault());
    const handlers = {
      onFirstNameChange: vi.fn(),
      onMiddleNameChange: vi.fn(),
      onLastNameChange: vi.fn(),
      onOrganizationTypeChange: vi.fn(),
      onOrganizationChange: vi.fn(),
      onTitleChange: vi.fn(),
    };

    render(
      <ProfileStep
        firstName="Ada"
        middleName=""
        lastName="Lovelace"
        organizationType="organization"
        organization="UC Merced"
        title="Engineer"
        saving={false}
        onSubmit={onSubmit}
        {...handlers}
      />,
    );

    fireEvent.change(screen.getByLabelText(/First Name/), {target: {value: 'Grace'}});
    expect(handlers.onFirstNameChange).toHaveBeenCalledWith('Grace');
    fireEvent.change(screen.getByLabelText(/Middle Name/), {target: {value: 'B.'}});
    expect(handlers.onMiddleNameChange).toHaveBeenCalledWith('B.');
    fireEvent.change(screen.getByLabelText(/Last Name/), {target: {value: 'Hopper'}});
    expect(handlers.onLastNameChange).toHaveBeenCalledWith('Hopper');
    fireEvent.click(screen.getByRole('button', {name: 'Individual'}));
    expect(handlers.onOrganizationTypeChange).toHaveBeenCalledWith('individual');
    fireEvent.change(screen.getByPlaceholderText('Company or organization name'), {target: {value: 'NASA'}});
    expect(handlers.onOrganizationChange).toHaveBeenCalledWith('NASA');
    fireEvent.change(screen.getByLabelText(/Title/), {target: {value: 'Director'}});
    expect(handlers.onTitleChange).toHaveBeenCalledWith('Director');
    fireEvent.submit(screen.getByRole('button', {name: 'Continue'}).closest('form')!);
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('disables incomplete and saving profile steps', () => {
    const {rerender} = render(
      <ProfileStep
        firstName=""
        middleName=""
        lastName="Lovelace"
        organizationType="individual"
        organization=""
        title=""
        saving={false}
        onFirstNameChange={vi.fn()}
        onMiddleNameChange={vi.fn()}
        onLastNameChange={vi.fn()}
        onOrganizationTypeChange={vi.fn()}
        onOrganizationChange={vi.fn()}
        onTitleChange={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', {name: 'Continue'})).toBeDisabled();
    expect(screen.queryByPlaceholderText('Company or organization name')).toBeNull();

    rerender(
      <ProfileStep
        firstName="Ada"
        middleName=""
        lastName="Lovelace"
        organizationType="organization"
        organization="UC Merced"
        title=""
        saving
        onFirstNameChange={vi.fn()}
        onMiddleNameChange={vi.fn()}
        onLastNameChange={vi.fn()}
        onOrganizationTypeChange={vi.fn()}
        onOrganizationChange={vi.fn()}
        onTitleChange={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', {name: /Saving/})).toBeDisabled();
  });

  it('extracts bounded subscribe API error messages', () => {
    expect(getSubscribeErrorMessage({response: {data: {detail: 'Already subscribed'}}})).toBe('Already subscribed');
    expect(getSubscribeErrorMessage({response: {data: {message: 'Check your email'}}})).toBe('Check your email');
    expect(
      getSubscribeErrorMessage({response: {data: {email: ['Email invalid'], non_field_errors: ['Try again']}}}),
    ).toBe('Email invalid Try again');
    expect(getSubscribeErrorMessage({response: {data: {detail: 'x'.repeat(301)}}})).toBe(
      'An unexpected error occurred. Please try again.',
    );
    expect(getSubscribeErrorMessage(null)).toBe('An unexpected error occurred. Please try again.');
  });
});
