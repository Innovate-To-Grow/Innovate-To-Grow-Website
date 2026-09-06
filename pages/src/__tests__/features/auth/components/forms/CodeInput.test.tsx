import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {
  CodeInput,
  VERIFICATION_CODE_PLACEHOLDER,
} from '@/features/auth/components/forms/CodeInput';

describe('CodeInput', () => {
  afterEach(() => {
    cleanup();
  });

  it('strips non-digits and slices to 6 on change', () => {
    const onChange = vi.fn();
    render(<CodeInput value="" onChange={onChange} />);
    fireEvent.change(screen.getByRole('textbox'), {target: {value: '12a3b456789'}});
    expect(onChange).toHaveBeenCalledWith('123456');
  });

  it('keeps fewer than 6 digits unchanged', () => {
    const onChange = vi.fn();
    render(<CodeInput value="" onChange={onChange} />);
    fireEvent.change(screen.getByRole('textbox'), {target: {value: '1x2'}});
    expect(onChange).toHaveBeenCalledWith('12');
  });

  it('renders the fixed input attributes and default aria-label', () => {
    render(<CodeInput value="" onChange={vi.fn()} />);
    const input = screen.getByRole('textbox', {name: '6-digit verification code'});
    expect(input).toHaveAttribute('type', 'text');
    expect(input).toHaveAttribute('inputMode', 'numeric');
    expect(input).toHaveAttribute('pattern', '\\d{6}');
    expect(input).toHaveAttribute('autoComplete', 'one-time-code');
    expect(input).toHaveAttribute('placeholder', VERIFICATION_CODE_PLACEHOLDER);
    expect(input).toHaveClass('auth-code-input');
  });

  it('forwards disabled, required, and className', () => {
    render(<CodeInput value="" onChange={vi.fn()} disabled required className="custom" />);
    const input = screen.getByRole('textbox');
    expect(input).toBeDisabled();
    expect(input).toBeRequired();
    expect(input).toHaveClass('auth-code-input', 'custom');
  });

  it('drops the aria-label when an id is provided', () => {
    render(<CodeInput value="" onChange={vi.fn()} id="otp-input" />);
    const input = screen.getByRole('textbox');
    expect(input).toHaveAttribute('id', 'otp-input');
    expect(input).not.toHaveAttribute('aria-label');
  });

  it('focuses the input when autoFocus is set', () => {
    render(<CodeInput value="" onChange={vi.fn()} autoFocus />);
    expect(screen.getByRole('textbox')).toHaveFocus();
  });

  it('renders the provided value in the field', () => {
    render(<CodeInput value="123456" onChange={vi.fn()} />);
    expect(screen.getByRole('textbox')).toHaveValue('123456');
  });
});
