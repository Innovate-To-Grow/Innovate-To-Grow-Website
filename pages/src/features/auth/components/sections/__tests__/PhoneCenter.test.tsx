import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PhoneCenter} from '../PhoneCenter';

const mocks = vi.hoisted(() => ({
  getContactPhones: vi.fn(),
  createContactPhone: vi.fn(),
  updateContactPhone: vi.fn(),
  deleteContactPhone: vi.fn(),
  requestContactPhoneVerification: vi.fn(),
  verifyContactPhoneCode: vi.fn(),
}));

vi.mock('@/features/auth/api', () => ({
  getContactPhones: () => mocks.getContactPhones(),
  createContactPhone: (data: unknown) => mocks.createContactPhone(data),
  updateContactPhone: (id: string, data: unknown) => mocks.updateContactPhone(id, data),
  deleteContactPhone: (id: string) => mocks.deleteContactPhone(id),
  requestContactPhoneVerification: (id: string) => mocks.requestContactPhoneVerification(id),
  verifyContactPhoneCode: (id: string, code: string) => mocks.verifyContactPhoneCode(id, code),
}));

describe('PhoneCenter add form', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getContactPhones.mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
  });

  it('renders optional phone copy with separate unchecked consent checkboxes', async () => {
    render(<PhoneCenter />);

    fireEvent.click(screen.getByRole('button', {name: 'Add Phone'}));

    expect(await screen.findByText('The phone number field is optional.')).toBeInTheDocument();
    expect(screen.getByLabelText(/receive course updates and educational reminders/i)).not.toBeChecked();
    expect(screen.getByLabelText(/accept Terms of Service & Privacy Policy/i)).not.toBeChecked();
    expect(screen.getByRole('link', {name: 'Terms of Service'})).toHaveAttribute(
      'href',
      'https://i2g.ucmerced.edu/privacy',
    );
    expect(screen.getByRole('link', {name: 'Privacy Policy'})).toHaveAttribute(
      'href',
      'https://www.ucmerced.edu/privacy-statement',
    );
  });

  it('allows submission without a phone number or SMS consent after terms acceptance', async () => {
    render(<PhoneCenter />);

    fireEvent.click(screen.getByRole('button', {name: 'Add Phone'}));
    fireEvent.click(await screen.findByLabelText(/accept Terms of Service & Privacy Policy/i));
    fireEvent.click(screen.getByRole('button', {name: 'Save Preferences'}));

    await waitFor(() => expect(screen.queryByText('The phone number field is optional.')).toBeNull());
    expect(mocks.createContactPhone).not.toHaveBeenCalled();
  });

  it('creates and verifies a phone only when a valid phone is provided', async () => {
    mocks.createContactPhone.mockResolvedValue({
      id: 'phone-1',
      phone_number: '5551234567',
      region: '1-US',
      region_display: 'United States',
      subscribe: true,
      verified: false,
    });
    mocks.requestContactPhoneVerification.mockResolvedValue({message: 'sent'});
    render(<PhoneCenter />);

    fireEvent.click(screen.getByRole('button', {name: 'Add Phone'}));
    fireEvent.change(await screen.findByLabelText('Phone Number'), {target: {value: '5551234567'}});
    fireEvent.click(screen.getByLabelText(/receive course updates and educational reminders/i));
    fireEvent.click(screen.getByLabelText(/accept Terms of Service & Privacy Policy/i));
    fireEvent.click(screen.getByRole('button', {name: 'Add Phone'}));

    await waitFor(() =>
      expect(mocks.createContactPhone).toHaveBeenCalledWith({
        phone_number: '5551234567',
        region: '1-US',
        subscribe: true,
      }),
    );
    expect(mocks.requestContactPhoneVerification).toHaveBeenCalledWith('phone-1');
  });

  it('keeps consent fields on the verification step before submitting the code', async () => {
    mocks.createContactPhone.mockResolvedValue({
      id: 'phone-1',
      phone_number: '5551234567',
      region: '1-US',
      region_display: 'United States',
      subscribe: true,
      verified: false,
    });
    mocks.requestContactPhoneVerification.mockResolvedValue({message: 'sent'});
    mocks.updateContactPhone.mockResolvedValue({
      id: 'phone-1',
      phone_number: '5551234567',
      region: '1-US',
      region_display: 'United States',
      subscribe: false,
      verified: false,
    });
    mocks.verifyContactPhoneCode.mockResolvedValue({
      id: 'phone-1',
      phone_number: '5551234567',
      region: '1-US',
      region_display: 'United States',
      subscribe: false,
      verified: true,
    });
    render(<PhoneCenter />);

    fireEvent.click(screen.getByRole('button', {name: 'Add Phone'}));
    fireEvent.change(await screen.findByLabelText('Phone Number'), {target: {value: '5551234567'}});
    fireEvent.click(screen.getByLabelText(/receive course updates and educational reminders/i));
    fireEvent.click(screen.getByLabelText(/accept Terms of Service & Privacy Policy/i));
    fireEvent.click(screen.getByRole('button', {name: 'Add Phone'}));

    expect(await screen.findByText('Verify phone number')).toBeInTheDocument();
    expect(screen.getByLabelText(/receive course updates and educational reminders/i)).toBeChecked();
    expect(screen.getByLabelText(/accept Terms of Service & Privacy Policy/i)).toBeChecked();
    expect(screen.getByRole('link', {name: 'Terms of Service'})).toHaveAttribute(
      'href',
      'https://i2g.ucmerced.edu/privacy',
    );
    expect(screen.getByRole('link', {name: 'Privacy Policy'})).toHaveAttribute(
      'href',
      'https://www.ucmerced.edu/privacy-statement',
    );

    fireEvent.change(screen.getByLabelText('6-digit verification code'), {target: {value: '123456'}});
    fireEvent.click(screen.getByLabelText(/accept Terms of Service & Privacy Policy/i));
    expect(screen.getByRole('button', {name: 'Submit code'})).toBeDisabled();

    fireEvent.click(screen.getByLabelText(/accept Terms of Service & Privacy Policy/i));
    fireEvent.click(screen.getByLabelText(/receive course updates and educational reminders/i));
    fireEvent.click(screen.getByRole('button', {name: 'Submit code'}));

    await waitFor(() => expect(mocks.updateContactPhone).toHaveBeenCalledWith('phone-1', {subscribe: false}));
    expect(mocks.verifyContactPhoneCode).toHaveBeenCalledWith('phone-1', '123456');
  });
});
