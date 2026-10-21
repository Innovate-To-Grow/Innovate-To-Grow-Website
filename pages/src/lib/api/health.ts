import { api } from './api-client';

// ======================== Health Check ========================

export interface HealthCheckResponse {
  status: 'ok' | 'error' | 'maintenance';
  database: string;
  maintenance: boolean;
  maintenance_message: string;
}

export interface HealthStatus {
  status: 'healthy' | 'maintenance' | 'degraded';
  isHealthy: boolean;
  maintenance: boolean;
  maintenanceMessage: string;
}

const healthFromResponse = (data: HealthCheckResponse): HealthStatus => {
  const maintenance = data.maintenance === true;
  return {
    status: maintenance ? 'maintenance' : data.status === 'ok' ? 'healthy' : 'degraded',
    isHealthy: !maintenance && data.status === 'ok',
    maintenance,
    maintenanceMessage: data.maintenance_message ?? '',
  };
};

const healthFromError = (error: unknown): HealthStatus => {
  // axios wraps non-2xx responses in an error, but 503 still has data
  const resp =
    error && typeof error === 'object' && 'response' in error
      ? (error as { response?: { data?: HealthCheckResponse } }).response
      : undefined;
  if (resp?.data?.maintenance) {
    return {
      status: 'maintenance',
      isHealthy: false,
      maintenance: true,
      maintenanceMessage: resp.data.maintenance_message ?? '',
    };
  }
  return {
    status: 'degraded',
    isHealthy: false,
    maintenance: false,
    maintenanceMessage: '',
  };
};

export const checkHealth = async (): Promise<HealthStatus> => {
  try {
    const response = await api.get<HealthCheckResponse>('/health/', {
      timeout: 5000, // 5 second timeout
    });
    return healthFromResponse(response.data);
  } catch (error) {
    return healthFromError(error);
  }
};

export const bypassMaintenance = async (password: string): Promise<{ success: boolean; error?: string }> => {
  try {
    const response = await api.post<{ success: boolean; error?: string }>('/maintenance/bypass/', { password });
    return response.data;
  } catch (error) {
    if (error && typeof error === 'object' && 'response' in error) {
      const resp = (error as { response?: { data?: { success: boolean; error?: string } } }).response;
      if (resp?.data) {
        return resp.data;
      }
    }
    return { success: false, error: 'Unable to verify password.' };
  }
};
