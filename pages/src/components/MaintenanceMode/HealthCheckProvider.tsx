import {
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import { checkHealth } from '../../services/api';
import { MaintenanceMode } from './MaintenanceMode';
import { HealthCheckContext, type HealthCheckContextType } from './context';
import './HealthCheckProvider.css';

interface HealthCheckProviderProps {
  children: ReactNode;
  /** Polling interval in milliseconds when service is down (default: 10000ms) */
  pollingInterval?: number;
  /** Initial check delay in milliseconds (default: 0ms) */
  initialDelay?: number;
}

/**
 * Health check gate for the app.
 * When backend is unavailable, it renders <MaintenanceMode />.
 */
export const HealthCheckProvider = ({
  children,
  pollingInterval = 10000,
  initialDelay = 0,
}: HealthCheckProviderProps) => {
  const [isHealthy, setIsHealthy] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [hasInitialized, setHasInitialized] = useState(false);
  const [maintenance, setMaintenance] = useState(false);
  const [maintenanceMessage, setMaintenanceMessage] = useState('');

  const performHealthCheck = useCallback(async () => {
    const result = await checkHealth();

    // If we transition from unhealthy to healthy, reload the page.
    // This ensures all independent React roots (MainMenu, Footer)
    // and the main app state are properly re-initialized.
    if (hasInitialized && !isHealthy && result.isHealthy) {
      window.location.reload();
      return result;
    }

    setIsHealthy(result.isHealthy);
    setMaintenance(result.maintenance);
    setMaintenanceMessage(result.maintenanceMessage);
    setIsLoading(false);
    return result;
  }, [isHealthy, hasInitialized]);

  // Initial health check
  useEffect(() => {
    const timeoutId = setTimeout(async () => {
      await performHealthCheck();
      setHasInitialized(true);
    }, initialDelay);

    return () => clearTimeout(timeoutId);
  }, [performHealthCheck, initialDelay]);

  // Polling when service is down
  useEffect(() => {
    if (!hasInitialized) return;
    if (isHealthy) return;

    const intervalId = setInterval(async () => {
      await performHealthCheck();
    }, pollingInterval);

    return () => clearInterval(intervalId);
  }, [isHealthy, hasInitialized, pollingInterval, performHealthCheck]);

  const checkNow = useCallback(async () => {
    setIsLoading(true);
    await performHealthCheck();
  }, [performHealthCheck]);

  const contextValue: HealthCheckContextType = {
    isHealthy,
    isLoading,
    maintenance,
    maintenanceMessage,
    checkNow,
  };

  // Render optimistically: show children while checking, only block on confirmed failure.
  // Before initialization completes or when healthy, render children normally.
  // Only show maintenance screen when the health check has completed and returned unhealthy.
  if (hasInitialized && !isHealthy) {
    return (
      <HealthCheckContext.Provider value={contextValue}>
        <MaintenanceMode message={maintenanceMessage} />
      </HealthCheckContext.Provider>
    );
  }

  return (
    <HealthCheckContext.Provider value={contextValue}>
      {children}
    </HealthCheckContext.Provider>
  );
};
