import axios from 'axios';

import {installRateLimitRetry} from './rateLimit';

// In development, Vite proxy will handle this
// In production, you may need to set this to your backend URL
// Default to /api so local dev can proxy backend requests without colliding
// with client-side routes like /pages/*
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// A 429 on a read waits out Retry-After and retries once; a final 429 carries a visitor-facing message.
installRateLimitRetry(api);

export { api };
