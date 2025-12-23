import { Outlet } from 'react-router-dom';
import './Layout.css';

export const Layout = () => {
  return (
    <div className="app-layout container">
      <Outlet />
    </div>
  );
};
