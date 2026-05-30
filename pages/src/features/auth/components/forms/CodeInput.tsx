import type { ChangeEvent } from 'react';

/** Use for any standalone OTP field that does not render `CodeInput`, so placeholder stays consistent. */
export const VERIFICATION_CODE_PLACEHOLDER = '000000';

interface CodeInputProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  /** When set, the visible <label htmlFor> can name the field; omit default aria-label. */
  id?: string;
  className?: string;
  autoFocus?: boolean;
  required?: boolean;
}

export const CodeInput = ({
  value,
  onChange,
  disabled = false,
  id,
  className,
  autoFocus = false,
  required = false,
}: CodeInputProps) => {
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextValue = event.target.value.replace(/\D/g, '').slice(0, 6);
    onChange(nextValue);
  };

  return (
    <input
      id={id}
      type="text"
      inputMode="numeric"
      pattern="\d{6}"
      autoComplete="one-time-code"
      autoFocus={autoFocus}
      required={required}
      className={['auth-code-input', className].filter(Boolean).join(' ')}
      value={value}
      onChange={handleChange}
      placeholder={VERIFICATION_CODE_PLACEHOLDER}
      disabled={disabled}
      aria-label={id ? undefined : '6-digit verification code'}
    />
  );
};
