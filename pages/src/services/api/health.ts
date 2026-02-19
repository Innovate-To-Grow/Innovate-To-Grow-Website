import api from './client';

// ======================== Health Check ========================

export interface HealthCheckResponse {
  status: 'ok' | 'error';
  database: string;
}

export const checkHealth = async (): Promise<boolean> => {
  try {
    const response = await api.get<HealthCheckResponse>('/health/', {
      timeout: 5000, // 5 second timeout
    });
    return response.data.status === 'ok';
  } catch {
    return false;
  }
};
