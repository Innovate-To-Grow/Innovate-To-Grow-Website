import { Outlet } from 'react-router-dom';
import './Container.css';

export const Container = () => {
  return (
    <div className="app-layout container">
      <Outlet />
    </div>
  );
};

