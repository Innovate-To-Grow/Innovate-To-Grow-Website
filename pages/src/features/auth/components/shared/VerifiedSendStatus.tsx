import {useEffect, useState} from 'react';

import {getVerifiedSendStatus, subscribeVerifiedSendStatus} from '@/features/auth/verification/status';
import type {VerifiedSendStatus as Status} from '@/features/auth/verification/types';

import './VerifiedSendStatus.css';

export const VerifiedSendStatus = () => {
  const [status, setStatus] = useState<Status>(getVerifiedSendStatus);

  useEffect(() => subscribeVerifiedSendStatus(setStatus), []);

  if (status.phase === 'idle' || status.phase === 'error' || !status.message) return null;

  return (
    <p
      className={`verified-send-status verified-send-status--${status.phase}`}
      role="status"
      aria-live="polite"
    >
      {status.message}
    </p>
  );
};
