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

export const checkHealth = async (): Promise<HealthStatus> => {
  try {
    const response = await api.get<HealthCheckResponse>('/health/', {
      timeout: 5000, // 5 second timeout
    });
    const maintenance = response.data.maintenance === true;
    return {
      status: maintenance ? 'maintenance' : response.data.status === 'ok' ? 'healthy' : 'degraded',
      isHealthy: !maintenance && response.data.status === 'ok',
      maintenance,
      maintenanceMessage: response.data.maintenance_message ?? '',
    };
  } catch (error) {
    // axios wraps non-2xx responses in an error, but 503 still has data
    if (error && typeof error === 'object' && 'response' in error) {
      const resp = (error as { response?: { data?: HealthCheckResponse } }).response;
      if (resp?.data?.maintenance) {
        return {
          status: 'maintenance',
          isHealthy: false,
          maintenance: true,
          maintenanceMessage: resp.data.maintenance_message ?? '',
        };
      }
    }
    return {
      status: 'degraded',
      isHealthy: false,
      maintenance: false,
      maintenanceMessage: '',
    };
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
