import { useRef, type KeyboardEvent, type ClipboardEvent } from 'react';

interface CodeInputProps {
  value: string;
  onChange: (code: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
  length?: number;
}

export const CodeInput = ({ value, onChange, disabled = false, autoFocus = true, length = 6 }: CodeInputProps) => {
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  const digits = Array.from({ length }, (_, i) => value[i] || '');

  const focusInput = (index: number) => {
    if (index >= 0 && index < length) {
      inputRefs.current[index]?.focus();
    }
  };

  const handleChange = (index: number, inputValue: string) => {
    // When a digit already exists and a new one is typed, inputValue may be 2 chars.
    // Strip non-digits and take the last character so the new digit wins.
    const char = inputValue.replace(/\D/g, '').slice(-1);
    if (char.length > 1) return; // safety guard
    const newDigits = [...digits];
    newDigits[index] = char;
    const newCode = newDigits.join('');
    onChange(newCode);
    if (char && index < length - 1) {
      focusInput(index + 1);
    }
  };

  const handleKeyDown = (index: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace') {
      if (digits[index]) {
        handleChange(index, '');
      } else if (index > 0) {
        focusInput(index - 1);
        handleChange(index - 1, '');
      }
      e.preventDefault();
    } else if (e.key === 'ArrowLeft' && index > 0) {
      focusInput(index - 1);
    } else if (e.key === 'ArrowRight' && index < length - 1) {
      focusInput(index + 1);
    }
  };

  const handlePaste = (e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, length);
    if (pasted) {
      onChange(pasted);
      focusInput(Math.min(pasted.length, length - 1));
    }
  };

  return (
    <div className="auth-code-inputs">
      {digits.map((digit, i) => (
        <input
          key={i}
          ref={(el) => { inputRefs.current[i] = el; }}
          type="text"
          inputMode="numeric"
          maxLength={1}
          className="auth-code-digit"
          value={digit}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={handlePaste}
          onFocus={(e) => e.target.select()}
          disabled={disabled}
          autoFocus={autoFocus && i === 0}
          autoComplete="one-time-code"
        />
      ))}
    </div>
  );
};
