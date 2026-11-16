import React from 'react';
import { Shield, Activity, User, LogOut } from 'lucide-react';

export default function Navbar({ user, onLogout, onOpenLogin, isOnline = true }) {
  return (
    <header className="h-16 border-b border-navy-800 bg-navy-900/90 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-40">
      {/* Brand */}
      <div className="flex items-center space-x-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-shield-cyan flex items-center justify-center shadow-lg shadow-cyan-500/20">
          <Shield className="w-6 h-6 text-navy-950 stroke-[2.5]" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <span className="font-extrabold text-lg tracking-tight bg-gradient-to-r from-white via-slate-200 to-cyan-400 bg-clip-text text-transparent">
              FraudShield AI
            </span>
            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-cyan-950/80 text-cyan-400 border border-cyan-800/60">
              v1.0 Hybrid
            </span>
          </div>
          <p className="text-xs text-slate-400 hidden sm:block">
            Intelligent Credit Card Fraud Detection & Risk Scoring
          </p>
        </div>
      </div>

      {/* Right Actions */}
      <div className="flex items-center space-x-4">
        {/* System Status Indicator */}
        <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-navy-850 border border-navy-700/60 text-xs">
          <span className="relative flex h-2.5 w-2.5">
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${isOnline ? 'bg-emerald-400' : 'bg-rose-400'}`}></span>
            <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${isOnline ? 'bg-emerald-500' : 'bg-rose-500'}`}></span>
          </span>
          <span className="text-slate-300 font-medium hidden md:inline">
            {isOnline ? 'Engine Online' : 'Connecting...'}
          </span>
        </div>

        {/* User Auth Section */}
        {user ? (
          <div className="flex items-center space-x-3 bg-navy-850 border border-navy-700/60 px-3 py-1.5 rounded-lg">
            <div className="w-7 h-7 rounded-full bg-cyan-900/60 text-cyan-300 flex items-center justify-center font-bold text-xs uppercase">
              {user.username.slice(0, 2)}
            </div>
            <div className="hidden lg:block text-left text-xs">
              <p className="font-semibold text-slate-200">{user.username}</p>
              <p className="text-[10px] text-cyan-400 capitalize">{user.role}</p>
            </div>
            <button
              onClick={onLogout}
              title="Sign Out"
              className="text-slate-400 hover:text-rose-400 transition-colors p-1"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <button
            onClick={onOpenLogin}
            className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-navy-950 font-semibold text-xs transition-all shadow-md shadow-cyan-600/20"
          >
            <User className="w-3.5 h-3.5" />
            <span>Analyst Login</span>
          </button>
        )}
      </div>
    </header>
  );
}
