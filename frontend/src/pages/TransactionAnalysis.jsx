import React, { useState } from 'react';
import { 
  Cpu, 
  ShieldAlert, 
  ShieldCheck, 
  AlertCircle, 
  Sparkles, 
  CheckCircle2,
  RefreshCw,
  Info
} from 'lucide-react';
import RiskBadge from '../components/RiskBadge';
import ShapChart from '../components/ShapChart';
import { predictTransaction } from '../services/api';

// Predefined genuine test presets
const PRESETS = {
  legitimate: {
    name: 'Legitimate Everyday Purchase',
    description: 'Normal $35.50 card purchase with standard PCA distribution',
    data: {
      Time: 12050.0,
      Amount: 35.50,
      V1: 0.124, V2: -0.052, V3: 0.982, V4: 0.412, V5: -0.210,
      V6: 0.150, V7: -0.120, V8: 0.080, V9: 0.320, V10: -0.110,
      V11: -0.450, V12: 0.230, V13: 0.650, V14: -0.180, V15: 0.890,
      V16: 0.120, V17: -0.050, V18: 0.020, V19: -0.150, V20: 0.040,
      V21: -0.080, V22: -0.120, V23: 0.050, V24: 0.180, V25: -0.210,
      V26: 0.110, V27: 0.020, V28: 0.010,
      notes: 'Grocery store in-person checkout'
    }
  },
  fraud: {
    name: 'High-Risk Account Takeover Fraud',
    description: 'Distinctive fraud signature with shifts on V4, V10, V14, V17',
    data: {
      Time: 406.0,
      Amount: 489.20,
      V1: -2.312, V2: 1.951, V3: -1.609, V4: 3.997, V5: -0.522,
      V6: -1.426, V7: -2.537, V8: 1.391, V9: -2.770, V10: -2.772,
      V11: 3.202, V12: -2.899, V13: -0.595, V14: -4.289, V15: 0.389,
      V16: -1.140, V17: -2.830, V18: -0.016, V19: 0.416, V20: 0.126,
      V21: 0.517, V22: -0.035, V23: -0.465, V24: 0.320, V25: 0.044,
      V26: 0.177, V27: 0.261, V28: -0.143,
      notes: 'Card not present online electronics purchase'
    }
  },
  anomaly: {
    name: 'Behavioral Outlier Spike',
    description: 'High-value $1,850.00 anomalous transaction triggering Isolation Forest',
    data: {
      Time: 86400.0,
      Amount: 1850.00,
      V1: -3.850, V2: 2.450, V3: -0.120, V4: 1.850, V5: -2.100,
      V6: 2.300, V7: -1.900, V8: 1.800, V9: -0.800, V10: -1.500,
      V11: 1.100, V12: -1.200, V13: 0.400, V14: -2.000, V15: -0.300,
      V16: -0.900, V17: -1.100, V18: 0.500, V19: 0.800, V20: 0.950,
      V21: 0.350, V22: -0.400, V23: 0.200, V24: -0.300, V25: 0.100,
      V26: -0.200, V27: 0.450, V28: 0.120,
      notes: 'International high-dollar wire simulation'
    }
  }
};

export default function TransactionAnalysis() {
  const [formData, setFormData] = useState(PRESETS.legitimate.data);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleInputChange = (field, value) => {
    setFormData((prev) => ({
      ...prev,
      [field]: field === 'notes' ? value : parseFloat(value) || 0,
    }));
  };

  const handleLoadPreset = (presetKey) => {
    setFormData(PRESETS[presetKey].data);
    setResult(null);
    setError(null);
  };

  const handleAnalyze = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await predictTransaction(formData);
      setResult(response);
    } catch (err) {
      console.error(err);
      setError(err.response?.data?.detail || 'Failed to analyze transaction.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Title */}
      <div>
        <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center space-x-2">
          <Cpu className="w-6 h-6 text-cyan-400" />
          <span>Real-Time Transaction Scoring Engine</span>
        </h1>
        <p className="text-sm text-slate-400">
          Input PCA components, Amount, and Time to evaluate fraud probability, anomaly status, and SHAP attribution.
        </p>
      </div>

      {/* Preset Quick Load Bar */}
      <div className="p-4 rounded-2xl bg-navy-900 border border-navy-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
        <div className="flex items-center space-x-2 text-xs font-semibold text-slate-300">
          <Sparkles className="w-4 h-4 text-cyan-400" />
          <span>Quick Benchmark Presets:</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {Object.entries(PRESETS).map(([key, item]) => (
            <button
              key={key}
              type="button"
              onClick={() => handleLoadPreset(key)}
              className="px-3 py-1.5 rounded-xl bg-navy-850 hover:bg-navy-800 border border-navy-700 text-xs font-medium text-slate-200 transition-colors"
            >
              {item.name}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Form Column */}
        <form onSubmit={handleAnalyze} className="lg:col-span-6 space-y-4">
          <div className="p-5 rounded-2xl bg-navy-900 border border-navy-800 shadow-xl space-y-4">
            <h3 className="font-bold text-white text-sm uppercase tracking-wider text-slate-300">
              Transaction Details
            </h3>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">
                  Amount ($ USD)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  value={formData.Amount}
                  onChange={(e) => handleInputChange('Amount', e.target.value)}
                  className="w-full px-3.5 py-2 rounded-xl bg-navy-850 border border-navy-700 text-white font-mono text-sm focus:outline-none focus:border-cyan-400"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">
                  Time (Elapsed Seconds)
                </label>
                <input
                  type="number"
                  step="1"
                  min="0"
                  required
                  value={formData.Time}
                  onChange={(e) => handleInputChange('Time', e.target.value)}
                  className="w-full px-3.5 py-2 rounded-xl bg-navy-850 border border-navy-700 text-white font-mono text-sm focus:outline-none focus:border-cyan-400"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1">
                Contextual Notes (Optional)
              </label>
              <input
                type="text"
                value={formData.notes || ''}
                onChange={(e) => handleInputChange('notes', e.target.value)}
                placeholder="e.g. Card present chip transaction"
                className="w-full px-3.5 py-2 rounded-xl bg-navy-850 border border-navy-700 text-white text-xs focus:outline-none focus:border-cyan-400"
              />
            </div>

            {/* PCA Features Grid */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-slate-400">
                  PCA Features (V1 to V28)
                </span>
                <span className="text-[11px] text-cyan-400 font-mono">
                  Standardized Components
                </span>
              </div>
              <div className="max-h-64 overflow-y-auto pr-2 grid grid-cols-2 sm:grid-cols-4 gap-2">
                {Array.from({ length: 28 }, (_, i) => i + 1).map((idx) => {
                  const key = `V${idx}`;
                  return (
                    <div key={key} className="space-y-0.5">
                      <label className="block text-[10px] text-slate-400 font-mono font-bold">
                        {key}
                      </label>
                      <input
                        type="number"
                        step="0.001"
                        required
                        value={formData[key] !== undefined ? formData[key] : 0}
                        onChange={(e) => handleInputChange(key, e.target.value)}
                        className="w-full px-2 py-1.5 rounded-lg bg-navy-850 border border-navy-700/80 text-white font-mono text-xs focus:outline-none focus:border-cyan-400 text-right"
                      />
                    </div>
                  );
                })}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-600 via-cyan-500 to-shield-cyan hover:opacity-95 text-navy-950 font-extrabold text-sm shadow-xl shadow-cyan-500/25 flex items-center justify-center space-x-2 transition-all disabled:opacity-50"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Evaluating Risk Pipeline...</span>
                </>
              ) : (
                <>
                  <Cpu className="w-4 h-4" />
                  <span>Execute Fraud Analysis</span>
                </>
              )}
            </button>
          </div>
        </form>

        {/* Prediction Results Column */}
        <div className="lg:col-span-6 space-y-4">
          {error && (
            <div className="p-4 rounded-xl bg-rose-950/80 border border-rose-800 text-rose-300 text-xs flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {result ? (
            <div className="p-5 rounded-2xl bg-navy-900 border border-navy-800 shadow-xl space-y-6 animate-fadeIn">
              {/* Verdict Header */}
              <div className="flex items-center justify-between pb-4 border-b border-navy-800">
                <div className="flex items-center space-x-3">
                  <div className={`p-3 rounded-2xl ${result.prediction === 'SUSPICIOUS' ? 'bg-rose-500/20 text-rose-400' : 'bg-emerald-500/20 text-emerald-400'}`}>
                    {result.prediction === 'SUSPICIOUS' ? <ShieldAlert className="w-7 h-7" /> : <ShieldCheck className="w-7 h-7" />}
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block">
                      Inference Verdict
                    </span>
                    <h3 className={`text-xl font-extrabold ${result.prediction === 'SUSPICIOUS' ? 'text-rose-400' : 'text-emerald-400'}`}>
                      {result.prediction}
                    </h3>
                  </div>
                </div>
                <RiskBadge category={result.risk_category} score={result.risk_score} />
              </div>

              {/* Gauges & Metrics */}
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3.5 rounded-xl bg-navy-850 border border-navy-800">
                  <span className="text-[10px] text-slate-400 uppercase font-bold">
                    Supervised Probability
                  </span>
                  <p className="text-xl font-extrabold text-cyan-400 mt-1 font-mono">
                    {result.fraud_probability_pct}%
                  </p>
                  <div className="w-full h-1.5 bg-navy-800 rounded-full mt-2 overflow-hidden">
                    <div
                      className={`h-full ${result.fraud_probability > 0.5 ? 'bg-rose-500' : 'bg-cyan-400'}`}
                      style={{ width: `${Math.min(100, result.fraud_probability_pct)}%` }}
                    ></div>
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-navy-850 border border-navy-800">
                  <span className="text-[10px] text-slate-400 uppercase font-bold">
                    Unsupervised Anomaly Status
                  </span>
                  <p className={`text-xl font-extrabold mt-1 font-mono ${result.is_anomaly ? 'text-amber-400' : 'text-slate-300'}`}>
                    {result.is_anomaly ? 'Outlier Flagged' : 'Inlier Baseline'}
                  </p>
                  <p className="text-[10px] text-slate-400 mt-1">
                    Normalized Anomaly Score: {result.anomaly_score}
                  </p>
                </div>
              </div>

              {/* SHAP Explainability Visualization */}
              {result.explanation && (
                <div>
                  <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-2 flex items-center space-x-1.5">
                    <Info className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Explainable AI Risk Attribution (SHAP)</span>
                  </h4>
                  <ShapChart
                    topFeatures={result.explanation.top_features}
                    summary={result.explanation.summary}
                  />
                </div>
              )}
            </div>
          ) : (
            <div className="p-12 rounded-2xl bg-navy-900 border border-navy-800/80 shadow-xl flex flex-col items-center justify-center text-center space-y-3 min-h-[420px]">
              <div className="w-14 h-14 rounded-2xl bg-navy-850 border border-navy-700 flex items-center justify-center text-slate-500">
                <Cpu className="w-7 h-7" />
              </div>
              <h4 className="text-base font-bold text-slate-300">Awaiting Transaction Parameters</h4>
              <p className="text-xs text-slate-500 max-w-sm">
                Select a benchmark preset above or enter custom transaction features, then click "Execute Fraud Analysis" to evaluate risk and view SHAP attribution.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
