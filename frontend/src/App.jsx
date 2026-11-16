import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import TransactionAnalysis from './pages/TransactionAnalysis';
import TransactionHistory from './pages/TransactionHistory';
import FraudAlerts from './pages/FraudAlerts';
import ModelPerformance from './pages/ModelPerformance';
import Settings from './pages/Settings';
import Login from './pages/Login';
import { getCurrentUser, getAlerts, getSystemHealth } from './services/api';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [user, setUser] = useState(null);
  const [showLogin, setShowLogin] = useState(false);
  const [alertCount, setAlertCount] = useState(0);
  const [isOnline, setIsOnline] = useState(true);

  // Initial authentication & health check
  useEffect(() => {
    const initApp = async () => {
      // Check health
      try {
        const health = await getSystemHealth();
        setIsOnline(health.status === 'healthy');
      } catch {
        setIsOnline(false);
      }

      // Check auth if token is stored
      const token = localStorage.getItem('fraudshield_token');
      if (token) {
        try {
          const userData = await getCurrentUser();
          setUser(userData);
        } catch {
          localStorage.removeItem('fraudshield_token');
          setUser(null);
        }
      }

      // Check pending alerts count
      try {
        const alerts = await getAlerts('PENDING');
        setAlertCount(alerts.length);
      } catch {
        // quiet
      }
    };

    initApp();
    const interval = setInterval(initApp, 30000); // 30s background sync
    return () => clearInterval(interval);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('fraudshield_token');
    setUser(null);
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <Dashboard onNavigateToAnalysis={() => setActiveTab('analysis')} />;
      case 'analysis':
        return <TransactionAnalysis />;
      case 'history':
        return <TransactionHistory />;
      case 'alerts':
        return (
          <FraudAlerts
            user={user}
            onRequireAuth={() => setShowLogin(true)}
          />
        );
      case 'performance':
        return <ModelPerformance />;
      case 'settings':
        return (
          <Settings
            user={user}
            onRequireAuth={() => setShowLogin(true)}
          />
        );
      default:
        return <Dashboard onNavigateToAnalysis={() => setActiveTab('analysis')} />;
    }
  };

  return (
    <div className="min-h-screen bg-navy-950 flex flex-col text-slate-100">
      <Navbar
        user={user}
        onLogout={handleLogout}
        onOpenLogin={() => setShowLogin(true)}
        isOnline={isOnline}
      />

      <div className="flex-1 flex overflow-hidden">
        <Sidebar
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          alertCount={alertCount}
        />

        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <div className="max-w-7xl mx-auto">
            {renderContent()}
          </div>
        </main>
      </div>

      {showLogin && (
        <Login
          onClose={() => setShowLogin(false)}
          onLoginSuccess={(u) => setUser(u)}
        />
      )}
    </div>
  );
}
