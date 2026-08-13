import { createContext, useContext } from 'react';

export interface HealthCheckContextType {
  status: 'healthy' | 'maintenance' | 'degraded';
  isHealthy: boolean;
  isLoading: boolean;
  maintenance: boolean;
  maintenanceMessage: string;
  checkNow: () => Promise<void>;
}

export const HealthCheckContext = createContext<HealthCheckContextType>({
  status: 'healthy',
  isHealthy: true,
  isLoading: true,
  maintenance: false,
  maintenanceMessage: '',
  checkNow: async () => {},
});

export const useHealthCheck = () => useContext(HealthCheckContext);
