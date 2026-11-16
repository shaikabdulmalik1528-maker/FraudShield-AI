import React from 'react';
import { ShieldAlert, ShieldCheck, AlertCircle } from 'lucide-react';

export default function RiskBadge({ category, score, showIcon = true }) {
  const cat = (category || 'LOW').toUpperCase();

  const configs = {
    LOW: {
      bg: 'bg-emerald-950/70 border-emerald-500/40 text-emerald-300',
      icon: ShieldCheck,
      label: 'Low Risk',
      dot: 'bg-emerald-400',
    },
    MEDIUM: {
      bg: 'bg-amber-950/70 border-amber-500/40 text-amber-300',
      icon: AlertCircle,
      label: 'Medium Risk',
      dot: 'bg-amber-400',
    },
    HIGH: {
      bg: 'bg-rose-950/70 border-rose-500/40 text-rose-300',
      icon: ShieldAlert,
      label: 'High Risk',
      dot: 'bg-rose-400',
    },
  };

  const conf = configs[cat] || configs.LOW;
  const Icon = conf.icon;

  return (
    <span className={`inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full border text-xs font-semibold ${conf.bg}`}>
      {showIcon && <Icon className="w-3.5 h-3.5" />}
      <span>{conf.label}</span>
      {score !== undefined && score !== null && (
        <span className="font-mono ml-1 font-bold">({score})</span>
      )}
    </span>
  );
}
