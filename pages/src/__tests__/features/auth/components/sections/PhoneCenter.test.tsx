import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PhoneCenter} from '@/features/auth/components/sections/PhoneCenter';

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

const renderPhoneCenter = () =>
  render(
    <MemoryRouter>
      <PhoneCenter />
    </MemoryRouter>,
  );

describe('PhoneCenter add form', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getContactPhones.mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
  });

  it('renders a required phone field with separate unchecked consent checkboxes', async () => {
    renderPhoneCenter();

    fireEvent.click(screen.getByRole('button', {name: 'Add Phone'}));

    expect(await screen.findByLabelText('Phone Number')).toBeRequired();
    expect(screen.queryByText(/optional/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/receive text messages from Innovate to Grow/i)).not.toBeChecked();
    expect(screen.getByLabelText(/I accept the Innovate to Grow/i)).not.toBeChecked();
    expect(screen.getByRole('link', {name: 'Privacy/Legal Notice'})).toHaveAttribute('href', '/privacy');
    expect(screen.getByRole('link', {name: 'Privacy Statement'})).toHaveAttribute(
      'href',
      'https://www.ucmerced.edu/privacy-statement',
    );
  });

  it('keeps the submit button disabled until a full phone number is entered', async () => {
    renderPhoneCenter();

    fireEvent.click(screen.getByRole('button', {name: 'Add Phone'}));
    fireEvent.click(await screen.findByLabelText(/I accept the Innovate to Grow/i));
    expect(screen.getByRole('button', {name: 'Add & Send Code'})).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Phone Number'), {target: {value: '555123'}});
    expect(screen.getByRole('button', {name: 'Add & Send Code'})).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Phone Number'), {target: {value: '5551234567'}});
    expect(screen.getByRole('button', {name: 'Add & Send Code'})).toBeEnabled();
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
    renderPhoneCenter();

    fireEvent.click(screen.getByRole('button', {name: 'Add Phone'}));
    fireEvent.change(await screen.findByLabelText('Phone Number'), {target: {value: '5551234567'}});
    fireEvent.click(screen.getByLabelText(/receive text messages from Innovate to Grow/i));
    fireEvent.click(screen.getByLabelText(/I accept the Innovate to Grow/i));
    fireEvent.click(screen.getByRole('button', {name: 'Add & Send Code'}));

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
    renderPhoneCenter();

    fireEvent.click(screen.getByRole('button', {name: 'Add Phone'}));
    fireEvent.change(await screen.findByLabelText('Phone Number'), {target: {value: '5551234567'}});
    fireEvent.click(screen.getByLabelText(/receive text messages from Innovate to Grow/i));
    fireEvent.click(screen.getByLabelText(/I accept the Innovate to Grow/i));
    fireEvent.click(screen.getByRole('button', {name: 'Add & Send Code'}));

    expect(await screen.findByText('Verify phone number')).toBeInTheDocument();
    expect(screen.getByLabelText(/receive text messages from Innovate to Grow/i)).toBeChecked();
    expect(screen.getByLabelText(/I accept the Innovate to Grow/i)).toBeChecked();
    expect(screen.getByRole('link', {name: 'Privacy/Legal Notice'})).toHaveAttribute('href', '/privacy');
    expect(screen.getByRole('link', {name: 'Privacy Statement'})).toHaveAttribute(
      'href',
      'https://www.ucmerced.edu/privacy-statement',
    );

    fireEvent.change(screen.getByLabelText('6-digit verification code'), {target: {value: '123456'}});
    fireEvent.click(screen.getByLabelText(/I accept the Innovate to Grow/i));
    expect(screen.getByRole('button', {name: 'Submit code'})).toBeDisabled();

    fireEvent.click(screen.getByLabelText(/I accept the Innovate to Grow/i));
    fireEvent.click(screen.getByLabelText(/receive text messages from Innovate to Grow/i));
    fireEvent.click(screen.getByRole('button', {name: 'Submit code'}));

    await waitFor(() => expect(mocks.updateContactPhone).toHaveBeenCalledWith('phone-1', {subscribe: false}));
    expect(mocks.verifyContactPhoneCode).toHaveBeenCalledWith('phone-1', '123456');
  });

  it('verifies an existing phone without requiring the add-phone terms state', async () => {
    mocks.getContactPhones.mockResolvedValue([
      {
        id: 'phone-existing',
        phone_number: '5559876543',
        region: '1-US',
        region_display: 'United States',
        subscribe: false,
        verified: false,
      },
    ]);
    mocks.requestContactPhoneVerification.mockResolvedValue({message: 'sent'});
    mocks.verifyContactPhoneCode.mockResolvedValue({
      id: 'phone-existing',
      phone_number: '5559876543',
      region: '1-US',
      region_display: 'United States',
      subscribe: false,
      verified: true,
    });

    renderPhoneCenter();
    fireEvent.click(await screen.findByRole('button', {name: 'Verify'}));
    fireEvent.change(
      await screen.findByLabelText('6-digit verification code'),
      {target: {value: '654321'}},
    );
    fireEvent.click(screen.getByRole('button', {name: 'Submit code'}));

    await waitFor(() =>
      expect(mocks.verifyContactPhoneCode).toHaveBeenCalledWith(
        'phone-existing',
        '654321',
      ),
    );
    expect(
      screen.queryByText(/Please accept Terms of Service/i),
    ).not.toBeInTheDocument();
  });
});
