import type { ChangeEvent } from 'react';

interface CodeInputProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export const CodeInput = ({ value, onChange, disabled = false }: CodeInputProps) => {
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextValue = event.target.value.replace(/\D/g, '').slice(0, 6);
    onChange(nextValue);
  };

  return (
    <input
      type="text"
      inputMode="numeric"
      pattern="\d{6}"
      autoComplete="one-time-code"
      className="auth-code-input"
      value={value}
      onChange={handleChange}
      placeholder="000000"
      disabled={disabled}
      aria-label="6-digit verification code"
    />
  );
};
