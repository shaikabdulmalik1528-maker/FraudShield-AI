import React, { useState, useEffect } from 'react';
import { 
  Settings as SettingsIcon, 
  ShieldCheck, 
  Sliders, 
  Database, 
  Server, 
  Check, 
  AlertCircle 
} from 'lucide-react';
import { getModelInfo, updateThreshold, getSystemHealth } from '../services/api';

export default function Settings({ user, onRequireAuth }) {
  const [modelInfo, setModelInfo] = useState(null);
  const [health, setHealth] = useState(null);
  const [threshold, setThreshold] = useState(0.895);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const [info, h] = await Promise.all([
        getModelInfo(),
        getSystemHealth()
      ]);
      setModelInfo(info);
      setHealth(h);
      if (info?.active_threshold) {
        setThreshold(info.active_threshold);
      }
    } catch (err) {
      console.error('Failed to load settings:', err);
    }
  };

  const handleSaveThreshold = async (e) => {
    e.preventDefault();
    if (!user) {
      onRequireAuth();
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      await updateThreshold(parseFloat(threshold));
      setMessage({ type: 'success', text: `Decision threshold successfully updated to ${threshold}!` });
      loadSettings();
    } catch (err) {
      console.error(err);
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to update threshold. Requires admin role.' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Title */}
      <div>
        <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center space-x-2">
          <SettingsIcon className="w-6 h-6 text-cyan-400" />
          <span>System Settings & Operational Parameters</span>
        </h1>
        <p className="text-sm text-slate-400">
          Configure runtime decision boundaries, risk thresholds, and inspect active pipeline health
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Threshold Adjustment Card */}
        <form onSubmit={handleSaveThreshold} className="p-6 rounded-2xl bg-navy-900 border border-navy-800 shadow-xl space-y-5">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-xl bg-cyan-950 text-cyan-400 border border-cyan-800">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-white text-base">Model Decision Threshold</h3>
              <p className="text-xs text-slate-400">Adjust the cutoff for flagging suspicious transactions</p>
            </div>
          </div>

          {message && (
            <div className={`p-3 rounded-xl text-xs flex items-center space-x-2 ${message.type === 'success' ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-800' : 'bg-rose-950/80 text-rose-300 border border-rose-800'}`}>
              {message.type === 'success' ? <Check className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
              <span>{message.text}</span>
            </div>
          )}

          <div>
            <div className="flex justify-between text-xs font-semibold mb-2">
              <span className="text-slate-300">Decision Cutoff:</span>
              <span className="text-cyan-400 font-mono text-sm font-bold">{threshold}</span>
            </div>
            <input
              type="range"
              min="0.10"
              max="0.95"
              step="0.005"
              value={threshold}
              onChange={(e) => setThreshold(parseFloat(e.target.value))}
              className="w-full accent-cyan-400 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-slate-500 mt-1">
              <span>0.10 (High Sensitivity / Higher False Positives)</span>
              <span>0.95 (High Precision / Low False Alarms)</span>
            </div>
          </div>

          <div className="p-3.5 rounded-xl bg-navy-850 text-xs text-slate-400 leading-relaxed">
            <p>
              The optimal threshold was tuned on validation data to maximize the <strong>F1-score</strong>. Lowering the threshold catches more fraud earlier at the expense of more manual review alerts.
            </p>
          </div>

          <button
            type="submit"
            disabled={saving}
            className="w-full py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-navy-950 font-bold text-xs transition-colors"
          >
            {saving ? 'Applying...' : 'Update Active Threshold'}
          </button>
        </form>

        {/* Runtime Pipeline Specs */}
        <div className="p-6 rounded-2xl bg-navy-900 border border-navy-800 shadow-xl space-y-4">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-xl bg-emerald-950 text-emerald-400 border border-emerald-800">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-white text-base">Pipeline Specification</h3>
              <p className="text-xs text-slate-400">Environment and model artifact specifications</p>
            </div>
          </div>

          <div className="divide-y divide-navy-800/80 text-xs">
            <div className="py-2.5 flex justify-between">
              <span className="text-slate-400">Champion Algorithm:</span>
              <span className="text-white font-semibold font-mono">{modelInfo?.champion_model || 'XGBoost'}</span>
            </div>
            <div className="py-2.5 flex justify-between">
              <span className="text-slate-400">Model Version:</span>
              <span className="text-cyan-400 font-semibold font-mono">v{modelInfo?.version || '1.0.0'}</span>
            </div>
            <div className="py-2.5 flex justify-between">
              <span className="text-slate-400">Dataset Training Size:</span>
              <span className="text-white font-mono">{modelInfo?.dataset_rows?.toLocaleString() || '283,726'} transactions</span>
            </div>
            <div className="py-2.5 flex justify-between">
              <span className="text-slate-400">Anomaly Layer:</span>
              <span className="text-white font-mono">Isolation Forest (contamination 0.5%)</span>
            </div>
            <div className="py-2.5 flex justify-between">
              <span className="text-slate-400">Risk Weights:</span>
              <span className="text-white font-mono">75% Supervised + 25% Unsupervised</span>
            </div>
            <div className="py-2.5 flex justify-between">
              <span className="text-slate-400">Database Engine:</span>
              <span className="text-emerald-400 font-mono">SQLAlchemy (Dual SQLite / Postgres)</span>
            </div>
            <div className="py-2.5 flex justify-between">
              <span className="text-slate-400">Engine Health:</span>
              <span className="text-emerald-400 font-bold uppercase">{health?.status || 'Online'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
