import React from 'react';

export default function StatCard({ title, value, subtitle, icon: Icon, color = 'cyan', change = null }) {
  const colorMap = {
    cyan: 'border-cyan-500/20 bg-gradient-to-br from-navy-900 to-navy-850 text-cyan-400',
    rose: 'border-rose-500/20 bg-gradient-to-br from-navy-900 to-navy-850 text-rose-400',
    emerald: 'border-emerald-500/20 bg-gradient-to-br from-navy-900 to-navy-850 text-emerald-400',
    amber: 'border-amber-500/20 bg-gradient-to-br from-navy-900 to-navy-850 text-amber-400',
    purple: 'border-purple-500/20 bg-gradient-to-br from-navy-900 to-navy-850 text-purple-400',
  };

  return (
    <div className={`p-5 rounded-2xl border ${colorMap[color]} shadow-lg transition-transform hover:-translate-y-0.5`}>
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{title}</p>
        {Icon && (
          <div className="p-2.5 rounded-xl bg-navy-800/80 border border-navy-700/60">
            <Icon className="w-5 h-5" />
          </div>
        )}
      </div>

      <div className="mt-3">
        <h3 className="text-2xl lg:text-3xl font-extrabold text-white tracking-tight">{value}</h3>
      </div>

      <div className="mt-2 flex items-center justify-between text-xs">
        <span className="text-slate-400">{subtitle}</span>
        {change && (
          <span className="font-semibold text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-800/40">
            {change}
          </span>
        )}
      </div>
    </div>
  );
}
