import {fireEvent, render, screen} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {EmailCenter} from '@/features/auth/components/sections/EmailCenter';
import {PhoneCenter} from '@/features/auth/components/sections/PhoneCenter';
import type {ContactEmail, ContactPhone, ProfileResponse} from '@/features/auth/api';

const mockUseEmailCenter = vi.fn();
const mockUsePhoneCenter = vi.fn();

vi.mock('@/features/auth/components/sections/internal/useEmailCenter', () => ({
  useEmailCenter: () => mockUseEmailCenter(),
}));

vi.mock('@/features/auth/components/sections/internal/usePhoneCenter', () => ({
  usePhoneCenter: () => mockUsePhoneCenter(),
}));

const profile: ProfileResponse = {
  member_uuid: 'member-1',
  email: 'ada@example.com',
  email_verified: false,
  primary_email_id: null,
  first_name: 'Ada',
  middle_name: '',
  last_name: 'Lovelace',
  organization: 'UC Merced',
  title: '',
  email_subscribe: true,
  is_staff: false,
  is_active: true,
  date_joined: '',
};

const contactEmail: ContactEmail = {
  id: 'email-1',
  email_address: 'other@example.com',
  email_type: 'other',
  subscribe: false,
  verified: false,
  created_at: '',
};

const phone: ContactPhone = {
  id: 'phone-1',
  phone_number: '+15551234567',
  region: '1-US',
  region_display: 'United States',
  subscribe: false,
  verified: false,
  created_at: '',
};

const emailCenter = (overrides = {}) => ({
  successMessage: null,
  error: null,
  subscribeSaving: false,
  primaryVerifying: false,
  primaryVerifyCode: '',
  primaryVerifyLoading: false,
  primaryVerifyError: null,
  primaryResendLoading: false,
  handlePrimarySubscribeToggle: vi.fn(),
  handlePrimaryToggleVerify: vi.fn(),
  setPrimaryVerifyCode: vi.fn(),
  handlePrimaryVerifySubmit: vi.fn(),
  handlePrimaryResend: vi.fn(),
  handlePrimaryCancelVerify: vi.fn(),
  loading: false,
  contactEmails: [contactEmail],
  verifyingId: null,
  verifyCode: '',
  verifyLoading: false,
  verifyError: null,
  resendLoading: false,
  handleContactTypeChange: vi.fn(),
  handleContactSubscribeToggle: vi.fn(),
  handleContactRequestVerification: vi.fn(),
  setVerifyCode: vi.fn(),
  handleVerifySubmit: vi.fn(),
  handleResend: vi.fn(),
  handleDelete: vi.fn(),
  setVerifyingId: vi.fn(),
  setVerifyError: vi.fn(),
  handleMakePrimary: vi.fn(),
  makePrimaryLoadingId: null,
  hasSecondaryEmail: false,
  showAddForm: false,
  addEmail: '',
  addType: 'secondary',
  addSubscribe: true,
  addLoading: false,
  addError: null,
  setAddEmail: vi.fn(),
  setAddType: vi.fn(),
  setAddSubscribe: vi.fn(),
  handleAddSubmit: vi.fn(),
  setShowAddForm: vi.fn(),
  setAddError: vi.fn(),
  clearMessages: vi.fn(),
  ...overrides,
});

const phoneCenter = (overrides = {}) => ({
  successMessage: null,
  error: null,
  loading: false,
  phones: [phone],
  verifyingId: null,
  verifyCode: '',
  verifyLoading: false,
  verifyError: null,
  resendLoading: false,
  handleSubscribeToggle: vi.fn(),
  handleToggleVerify: vi.fn(),
  setVerifyCode: vi.fn(),
  handleVerifySubmit: vi.fn(),
  handleResend: vi.fn(),
  handleCancelVerify: vi.fn(),
  handleDelete: vi.fn(),
  showAddForm: false,
  pendingNewPhone: null,
  addRegion: '1-US',
  addPhoneNumber: '',
  addSubscribe: true,
  addLoading: false,
  addError: null,
  handleAddRegionChange: vi.fn(),
  setAddPhoneNumber: vi.fn(),
  setAddSubscribe: vi.fn(),
  handleAddSubmit: vi.fn(),
  setShowAddForm: vi.fn(),
  setAddError: vi.fn(),
  beginAddPhoneFlow: vi.fn(),
  handleResendPendingPhone: vi.fn(),
  handleAbandonPendingPhone: vi.fn(),
  abandonPendingLoading: false,
  ...overrides,
});

describe('account email and phone centers', () => {
  beforeEach(() => {
    mockUseEmailCenter.mockReset();
    mockUsePhoneCenter.mockReset();
  });

  it('renders email center status, loading state, and add button actions', () => {
    const state = emailCenter({
      successMessage: 'Email saved.',
      error: 'Email failed.',
      loading: true,
      contactEmails: [],
      hasSecondaryEmail: true,
    });
    mockUseEmailCenter.mockReturnValue(state);

    render(<EmailCenter profile={profile} onProfileUpdate={vi.fn()} />);

    expect(screen.getByText('Email saved.')).toBeInTheDocument();
    expect(screen.getByText('Email failed.')).toBeInTheDocument();
    expect(screen.getByText('Loading connected emails...')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Add Email'}));
    expect(state.setShowAddForm).toHaveBeenCalledWith(true);
    expect(state.setAddType).toHaveBeenCalledWith('other');
    expect(state.clearMessages).toHaveBeenCalledTimes(1);
  });

  it('renders and cancels the email add form', () => {
    const state = emailCenter({showAddForm: true, addEmail: 'new@example.com', addError: 'Duplicate'});
    mockUseEmailCenter.mockReturnValue(state);

    render(<EmailCenter profile={profile} onProfileUpdate={vi.fn()} />);

    expect(screen.getByText('Duplicate')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
    expect(state.setShowAddForm).toHaveBeenCalledWith(false);
    expect(state.setAddError).toHaveBeenCalledWith(null);
  });

  it('renders phone center empty and loading states and starts add flow', () => {
    const state = phoneCenter({loading: false, phones: [], successMessage: 'Phone saved.', error: 'Phone failed.'});
    mockUsePhoneCenter.mockReturnValue(state);

    render(<PhoneCenter />);

    expect(screen.getByText('Phone saved.')).toBeInTheDocument();
    expect(screen.getByText('Phone failed.')).toBeInTheDocument();
    expect(screen.getByText('No phone numbers added yet.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Add Phone'}));
    expect(state.beginAddPhoneFlow).toHaveBeenCalledTimes(1);
  });

  it('renders phone add and pending verification forms with cancel actions', () => {
    const addState = phoneCenter({showAddForm: true, phones: [], addPhoneNumber: '5551234567', addError: 'Invalid'});
    mockUsePhoneCenter.mockReturnValue(addState);

    const {unmount} = render(<PhoneCenter />);

    expect(screen.getByText('Invalid')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
    expect(addState.setShowAddForm).toHaveBeenCalledWith(false);
    expect(addState.setAddError).toHaveBeenCalledWith(null);

    unmount();

    const pendingState = phoneCenter({
      showAddForm: true,
      phones: [],
      pendingNewPhone: phone,
      verifyCode: '123456',
    });
    mockUsePhoneCenter.mockReturnValue(pendingState);

    render(<PhoneCenter />);

    fireEvent.click(screen.getByRole('button', {name: 'Resend Code'}));
    expect(pendingState.handleResendPendingPhone).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', {name: 'Discard number'}));
    expect(pendingState.handleAbandonPendingPhone).toHaveBeenCalledTimes(1);
  });
});
