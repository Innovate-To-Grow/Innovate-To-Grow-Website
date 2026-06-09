import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';

import {CompleteProfileForm} from '@/features/auth/components/pages/CompleteProfileForm';

const renderForm = (overrides: Partial<Parameters<typeof CompleteProfileForm>[0]> = {}) => {
  const props = {
    firstName: 'Ada',
    middleName: 'Byron',
    lastName: 'Lovelace',
    organizationType: 'organization' as const,
    organization: 'Acme Corp',
    title: 'Director',
    isSaving: false,
    setFirstName: vi.fn(),
    setMiddleName: vi.fn(),
    setLastName: vi.fn(),
    onOrganizationTypeChange: vi.fn(),
    setOrganization: vi.fn(),
    setTitle: vi.fn(),
    clearError: vi.fn(),
    onSubmit: vi.fn((event) => event.preventDefault()),
    ...overrides,
  };

  render(<CompleteProfileForm {...props} />);
  return props;
};

describe('CompleteProfileForm', () => {
  it('forwards field edits, organization toggles, and submit events', () => {
    const props = renderForm();

    fireEvent.change(screen.getByLabelText('First Name'), {target: {value: 'Grace'}});
    expect(props.setFirstName).toHaveBeenCalledWith('Grace');

    fireEvent.change(screen.getByLabelText(/Middle Name/), {target: {value: 'B.'}});
    expect(props.setMiddleName).toHaveBeenCalledWith('B.');

    fireEvent.change(screen.getByLabelText('Last Name'), {target: {value: 'Hopper'}});
    expect(props.setLastName).toHaveBeenCalledWith('Hopper');

    fireEvent.change(screen.getByPlaceholderText('Company or organization name'), {target: {value: 'Navy'}});
    expect(props.setOrganization).toHaveBeenCalledWith('Navy');

    fireEvent.change(screen.getByLabelText(/Title/), {target: {value: 'Rear Admiral'}});
    expect(props.setTitle).toHaveBeenCalledWith('Rear Admiral');

    fireEvent.click(screen.getByRole('button', {name: 'Individual'}));
    expect(props.onOrganizationTypeChange).toHaveBeenCalledWith('individual');

    fireEvent.click(screen.getByRole('button', {name: 'Organization'}));
    expect(props.onOrganizationTypeChange).toHaveBeenCalledWith('organization');

    fireEvent.submit(screen.getByRole('button', {name: 'Continue to Account'}).closest('form')!);
    expect(props.onSubmit).toHaveBeenCalled();
    expect(props.clearError).toHaveBeenCalledTimes(7);
  });

  it('hides organization-only fields for individuals and renders the saving state', () => {
    renderForm({
      organizationType: 'individual',
      organization: '',
      title: '',
      isSaving: true,
    });

    expect(screen.queryByPlaceholderText('Company or organization name')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Title/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: /Saving profile/})).toBeDisabled();
  });
});
