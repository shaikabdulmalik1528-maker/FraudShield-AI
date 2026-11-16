import React from 'react';
import { 
  LayoutDashboard, 
  Cpu, 
  History, 
  AlertTriangle, 
  BarChart3, 
  Settings, 
  ShieldCheck 
} from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab, alertCount = 0 }) {
  const menuItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'analysis', label: 'Transaction Analysis', icon: Cpu },
    { id: 'history', label: 'Transaction History', icon: History },
    { id: 'alerts', label: 'Fraud Alerts', icon: AlertTriangle, badge: alertCount },
    { id: 'performance', label: 'Model Performance', icon: BarChart3 },
    { id: 'settings', label: 'System Settings', icon: Settings },
  ];

  return (
    <aside className="w-64 border-r border-navy-800 bg-navy-900/60 flex flex-col shrink-0 min-h-[calc(100vh-4rem)]">
      <div className="p-4 space-y-1">
        <p className="px-3 text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">
          Operations
        </p>
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl font-medium text-sm transition-all ${
                isActive
                  ? 'bg-gradient-to-r from-cyan-950/80 to-navy-800 text-cyan-300 border-l-4 border-cyan-400 font-semibold shadow-inner'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-navy-850/60'
              }`}
            >
              <div className="flex items-center space-x-3">
                <Icon className={`w-4 h-4 ${isActive ? 'text-cyan-400' : 'text-slate-400'}`} />
                <span>{item.label}</span>
              </div>
              {item.badge > 0 && (
                <span className="px-2 py-0.5 text-xs font-bold rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40">
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="mt-auto p-4 border-t border-navy-800/80">
        <div className="p-3 rounded-xl bg-navy-850/80 border border-navy-700/60">
          <div className="flex items-center space-x-2 text-xs font-semibold text-slate-200 mb-1">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Active Pipeline</span>
          </div>
          <p className="text-[11px] text-slate-400">
            XGBoost (80.5% PR-AUC) + Isolation Forest anomaly layer with local SHAP force tree.
          </p>
        </div>
      </div>
    </aside>
  );
}
