import {useEffect, useState} from 'react';

import {getVerifiedSendStatus, subscribeVerifiedSendStatus} from './status';
import type {VerifiedSendStatus as Status} from './types';

import './VerifiedSendStatus.css';

export const VerifiedSendStatus = () => {
  const [status, setStatus] = useState<Status>(getVerifiedSendStatus);

  useEffect(() => subscribeVerifiedSendStatus(setStatus), []);

  if (status.phase === 'idle' || !status.message) return null;

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
