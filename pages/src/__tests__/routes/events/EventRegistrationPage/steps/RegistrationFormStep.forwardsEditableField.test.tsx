import {act, cleanup, fireEvent, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {renderForm, submitForm} from '@/__tests__/routes/events/EventRegistrationPage/steps/registrationFormStepFixtures';

describe('RegistrationFormStep', () => {
  afterEach(() => {
    cleanup();
  });

  it('forwards editable field changes', () => {
    const handlers = {
      onFirstNameChange: vi.fn(),
      onMiddleNameChange: vi.fn(),
      onLastNameChange: vi.fn(),
      onOrganizationChange: vi.fn(),
      onTitleChange: vi.fn(),
      onOrgTypeChange: vi.fn(),
    };
    renderForm({}, {attendeeOrgType: 'organization', ...handlers});

    fireEvent.change(screen.getByLabelText(/First Name/), {target: {value: 'A'}});
    fireEvent.change(screen.getByLabelText(/Middle Name/), {target: {value: 'B'}});
    fireEvent.change(screen.getByLabelText(/Last Name/), {target: {value: 'C'}});
    fireEvent.change(screen.getByPlaceholderText('Company or organization name'), {target: {value: 'Org'}});
    fireEvent.change(screen.getByPlaceholderText('Your title or position (e.g. CEO, Director)'), {target: {value: 'T'}});
    fireEvent.click(screen.getByRole('button', {name: 'Organization'}));
    fireEvent.click(screen.getByRole('button', {name: 'Individual'}));

    expect(handlers.onFirstNameChange).toHaveBeenCalledWith('A');
    expect(handlers.onMiddleNameChange).toHaveBeenCalledWith('B');
    expect(handlers.onLastNameChange).toHaveBeenCalledWith('C');
    expect(handlers.onOrganizationChange).toHaveBeenCalledWith('Org');
    expect(handlers.onTitleChange).toHaveBeenCalledWith('T');
    expect(handlers.onOrgTypeChange).toHaveBeenCalledWith('organization');
    expect(handlers.onOrgTypeChange).toHaveBeenCalledWith('individual');
  });

  it('forwards secondary email, phone, and phone code changes', () => {
    const onSecondaryEmailChange = vi.fn();
    const onPhoneChange = vi.fn();
    const onPhoneCodeChange = vi.fn();
    renderForm(
      {allow_secondary_email: true, collect_phone: true, verify_phone: true},
      {
        phoneCodeSent: true,
        phoneCode: '',
        onSecondaryEmailChange,
        onPhoneChange,
        onPhoneCodeChange,
      },
    );

    fireEvent.change(screen.getByLabelText(/Secondary Email/), {target: {value: 'x@example.com'}});
    fireEvent.change(screen.getByLabelText(/Phone Number/), {target: {value: '(202) 555-0123'}});
    fireEvent.focus(screen.getByLabelText(/Phone Number/));
    fireEvent.blur(screen.getByLabelText(/Phone Number/));
    fireEvent.change(screen.getByLabelText('Phone verification code'), {target: {value: '123456'}});

    expect(onSecondaryEmailChange).toHaveBeenCalledWith('x@example.com');
    expect(onPhoneChange).toHaveBeenCalledWith('2025550123');
    expect(onPhoneCodeChange).toHaveBeenCalledWith('123456');
  });

  it('scrolls the first errored group into view on a failed submit', () => {
    const scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;
    let rafCallback: FrameRequestCallback | null = null;
    const originalRaf = globalThis.requestAnimationFrame;
    globalThis.requestAnimationFrame = ((callback: FrameRequestCallback) => {
      rafCallback = callback;
      return 0;
    }) as unknown as typeof requestAnimationFrame;

    try {
      const {onSubmit} = renderForm({}, {attendeeLastName: ''});
      submitForm();

      expect(rafCallback).not.toBeNull();
      act(() => {
        rafCallback?.(0);
      });

      expect(scrollSpy).toHaveBeenCalledWith({behavior: 'smooth', block: 'center'});
      expect(onSubmit).not.toHaveBeenCalled();
    } finally {
      globalThis.requestAnimationFrame = originalRaf;
      delete (Element.prototype as unknown as Record<string, unknown>).scrollIntoView;
    }
  });
});
