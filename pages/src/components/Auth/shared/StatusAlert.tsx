import type {CSSProperties} from 'react';

interface StatusAlertProps {
  tone: 'error' | 'success' | 'info';
  message: string;
  style?: CSSProperties;
}

const ICON_BY_TONE = {
  error: 'fa-exclamation-circle',
  info: 'fa-info-circle',
  success: 'fa-check-circle',
} as const;

export const StatusAlert = ({tone, message, style}: StatusAlertProps) => (
  <div className={`auth-alert ${tone}`} role={tone === 'error' ? 'alert' : 'status'} style={style}>
    <i className={`fa ${ICON_BY_TONE[tone]} auth-alert-icon`} aria-hidden />
    <span>{message}</span>
  </div>
);
