import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {CompleteProfileForm} from '@/features/auth/components/pages/CompleteProfileForm';

type OrganizationType = 'individual' | 'organization';

const baseProps = () => ({
  firstName: 'Ada',
  middleName: '',
  lastName: 'Lovelace',
  organizationType: 'organization' as OrganizationType,
  organization: 'Acme Corp',
  title: 'CEO',
  isSaving: false,
  setFirstName: vi.fn(),
  setMiddleName: vi.fn(),
  setLastName: vi.fn(),
  onOrganizationTypeChange: vi.fn(),
  setOrganization: vi.fn(),
  setTitle: vi.fn(),
  clearError: vi.fn(),
  onSubmit: vi.fn(),
});

const renderForm = (overrides: Partial<ReturnType<typeof baseProps>> = {}) => {
  const props = {...baseProps(), ...overrides};
  render(<CompleteProfileForm {...props} />);
  return props;
};

describe('CompleteProfileForm', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders organization fields and submits the form', () => {
    const props = renderForm();

    expect(screen.getByLabelText('First Name')).toHaveValue('Ada');
    expect(screen.getByLabelText('Last Name')).toHaveValue('Lovelace');
    expect(screen.getByPlaceholderText('Company or organization name')).toHaveValue('Acme Corp');
    expect(screen.getByLabelText(/Title/)).toHaveValue('CEO');

    fireEvent.submit(screen.getByRole('button', {name: 'Continue to Account'}).closest('form')!);
    expect(props.onSubmit).toHaveBeenCalledOnce();
  });

  it('calls setters and clears errors as each field changes', () => {
    const props = renderForm();

    fireEvent.change(screen.getByLabelText('First Name'), {target: {value: 'Grace'}});
    fireEvent.change(screen.getByLabelText(/Middle Name/), {target: {value: 'B'}});
    fireEvent.change(screen.getByLabelText('Last Name'), {target: {value: 'Hopper'}});
    fireEvent.change(screen.getByPlaceholderText('Company or organization name'), {target: {value: 'Navy'}});
    fireEvent.change(screen.getByLabelText(/Title/), {target: {value: 'Admiral'}});

    expect(props.setFirstName).toHaveBeenCalledWith('Grace');
    expect(props.setMiddleName).toHaveBeenCalledWith('B');
    expect(props.setLastName).toHaveBeenCalledWith('Hopper');
    expect(props.setOrganization).toHaveBeenCalledWith('Navy');
    expect(props.setTitle).toHaveBeenCalledWith('Admiral');
    expect(props.clearError).toHaveBeenCalledTimes(5);
  });

  it('switches organization type via the toggle buttons', () => {
    const props = renderForm();

    fireEvent.click(screen.getByRole('button', {name: 'Individual'}));
    expect(props.onOrganizationTypeChange).toHaveBeenCalledWith('individual');

    fireEvent.click(screen.getByRole('button', {name: 'Organization'}));
    expect(props.onOrganizationTypeChange).toHaveBeenCalledWith('organization');
    expect(props.clearError).toHaveBeenCalledTimes(2);
  });

  it('hides organization and title fields for an individual', () => {
    renderForm({organizationType: 'individual', organization: '', title: ''});

    expect(screen.queryByPlaceholderText('Company or organization name')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Title/)).not.toBeInTheDocument();
  });

  it('disables the submit while saving and shows the spinner label', () => {
    renderForm({isSaving: true});

    expect(screen.getByRole('button', {name: 'Saving profile...'})).toBeDisabled();
  });

  it('disables the submit when first or last name is blank', () => {
    renderForm({firstName: '', lastName: ''});

    expect(screen.getByRole('button', {name: 'Continue to Account'})).toBeDisabled();
  });

  it('disables the submit when an organization account omits its name', () => {
    renderForm({organization: ''});

    expect(screen.getByRole('button', {name: 'Continue to Account'})).toBeDisabled();
  });

  it('enables the submit for an individual without an organization', () => {
    renderForm({organizationType: 'individual', organization: ''});

    expect(screen.getByRole('button', {name: 'Continue to Account'})).toBeEnabled();
  });
});
