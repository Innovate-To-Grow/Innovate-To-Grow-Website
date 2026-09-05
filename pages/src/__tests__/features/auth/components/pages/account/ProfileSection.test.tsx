import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {ProfileSection} from '@/features/auth/components/pages/account/ProfileSection';

type OrganizationType = 'individual' | 'organization';

const renderSection = (overrides: Record<string, unknown> = {}) => {
  const props = {
    firstName: 'Ada',
    middleName: '',
    lastName: 'Lovelace',
    organizationType: 'organization' as OrganizationType,
    organization: 'Acme Corp',
    title: 'CEO',
    profileImage: null,
    imageUploading: false,
    imageError: null,
    profileSaving: false,
    profileMessage: null,
    profileError: null,
    isEditingProfile: false,
    onImageChange: vi.fn(),
    onSubmit: vi.fn(),
    onFirstNameChange: vi.fn(),
    onMiddleNameChange: vi.fn(),
    onLastNameChange: vi.fn(),
    onOrganizationTypeChange: vi.fn(),
    onOrganizationChange: vi.fn(),
    onTitleChange: vi.fn(),
    onRetryProfile: vi.fn(),
    onStartEditing: vi.fn(),
    onCancelEditing: vi.fn(),
    ...overrides,
  };
  const view = render(<ProfileSection {...props} />);
  return {props, ...view};
};

describe('ProfileSection', () => {
  afterEach(cleanup);

  it('renders the profile image when one is provided', () => {
    renderSection({profileImage: '/media/a.png'});

    expect(screen.getByAltText('Profile')).toHaveAttribute('src', '/media/a.png');
  });

  it('renders initials from the first and last name', () => {
    renderSection({firstName: 'Ada', lastName: 'Lovelace'});

    expect(screen.getByText('AL')).toBeInTheDocument();
  });

  it('renders only the first initial when there is no last name', () => {
    renderSection({firstName: 'Ada', lastName: ''});

    expect(screen.getByText('A')).toBeInTheDocument();
  });

  it('renders the default placeholder for an empty name', () => {
    renderSection({firstName: '', lastName: ''});

    expect(screen.getByText('U')).toBeInTheDocument();
  });

  it('shows a spinner while the image uploads', () => {
    const {container} = renderSection({imageUploading: true});

    expect(container.querySelector('.auth-spinner')).toBeInTheDocument();
    expect(container.querySelector('svg')).not.toBeInTheDocument();
  });

  it('renders a non-HTML image error', () => {
    renderSection({imageError: 'Image size should be less than 5MB.'});

    expect(screen.getByText('Image size should be less than 5MB.')).toBeInTheDocument();
  });

  it('hides an HTML-like image error', () => {
    const {container} = renderSection({imageError: '<div>bad</div>'});

    expect(container.querySelector('.profile-image-error')).not.toBeInTheDocument();
  });

  it('renders the profile success message', () => {
    renderSection({profileMessage: 'Profile updated successfully.'});

    expect(screen.getByRole('status')).toHaveTextContent('Profile updated successfully.');
  });

  it('renders a profile error and retries loading', () => {
    const {props} = renderSection({profileError: 'Failed to load'});

    expect(screen.getByText('Failed to load')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Retry'}));
    expect(props.onRetryProfile).toHaveBeenCalled();
  });

  it('starts editing from the read-only view', () => {
    const {props} = renderSection();

    fireEvent.click(screen.getByRole('button', {name: 'Edit Profile'}));
    expect(props.onStartEditing).toHaveBeenCalled();
  });

  it('saves and cancels from the editing view', () => {
    const {props} = renderSection({isEditingProfile: true});

    fireEvent.submit(screen.getByRole('button', {name: 'Save Profile'}).closest('form')!);
    expect(props.onSubmit).toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
    expect(props.onCancelEditing).toHaveBeenCalled();
  });

  it('disables the name and organization inputs while not editing', () => {
    renderSection();

    expect(screen.getByLabelText('First Name')).toBeDisabled();
    expect(screen.getByLabelText('Middle Name')).toBeDisabled();
    expect(screen.getByLabelText('Last Name')).toBeDisabled();
    expect(screen.getByPlaceholderText('Company or organization name')).toBeDisabled();
    expect(screen.getByLabelText(/Title/)).toBeDisabled();
  });

  it('switches organization type through the toggle buttons', () => {
    const {props} = renderSection({isEditingProfile: true});

    fireEvent.click(screen.getByRole('button', {name: 'Individual'}));
    expect(props.onOrganizationTypeChange).toHaveBeenCalledWith('individual');

    fireEvent.click(screen.getByRole('button', {name: 'Organization'}));
    expect(props.onOrganizationTypeChange).toHaveBeenCalledWith('organization');
  });

  it('hides the organization and title inputs for individual accounts', () => {
    renderSection({organizationType: 'individual', organization: '', title: ''});

    expect(screen.queryByPlaceholderText('Company or organization name')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Title/)).not.toBeInTheDocument();
  });

  it('forwards field edits to the change handlers', () => {
    const {props} = renderSection({isEditingProfile: true});

    fireEvent.change(screen.getByLabelText('First Name'), {target: {value: 'Grace'}});
    fireEvent.change(screen.getByLabelText('Middle Name'), {target: {value: 'B'}});
    fireEvent.change(screen.getByLabelText('Last Name'), {target: {value: 'Hopper'}});
    fireEvent.change(screen.getByPlaceholderText('Company or organization name'), {target: {value: 'Navy'}});
    fireEvent.change(screen.getByLabelText(/Title/), {target: {value: 'Admiral'}});

    expect(props.onFirstNameChange).toHaveBeenCalledWith('Grace');
    expect(props.onMiddleNameChange).toHaveBeenCalledWith('B');
    expect(props.onLastNameChange).toHaveBeenCalledWith('Hopper');
    expect(props.onOrganizationChange).toHaveBeenCalledWith('Navy');
    expect(props.onTitleChange).toHaveBeenCalledWith('Admiral');
  });

  it('forwards image selection to the change handler', () => {
    const {props, container} = renderSection();
    const file = new File(['a'], 'a.png', {type: 'image/png'});
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    fireEvent.change(input, {target: {files: [file]}});
    expect(props.onImageChange).toHaveBeenCalled();
  });

  it('shows the saving label while the profile is being saved', () => {
    renderSection({isEditingProfile: true, profileSaving: true});

    expect(screen.getByText('Saving...')).toBeInTheDocument();
  });
});
