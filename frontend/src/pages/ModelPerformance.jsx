import React, { useState, useEffect } from 'react';
import { 
  BarChart3, 
  Award, 
  CheckCircle, 
  Info, 
  RefreshCw,
  TrendingUp,
  Sliders
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell
} from 'recharts';
import { getModelPerformance } from '../services/api';

export default function ModelPerformance() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchPerformance = async () => {
    setLoading(true);
    try {
      const res = await getModelPerformance();
      setData(res);
    } catch (err) {
      console.error('Failed to load performance metrics:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPerformance();
  }, []);

  if (loading) {
    return (
      <div className="p-12 text-center text-slate-400 text-xs">
        Loading model performance benchmark...
      </div>
    );
  }

  if (!data || data.status === 'not_trained') {
    return (
      <div className="p-12 text-center text-slate-400 bg-navy-900 rounded-2xl border border-navy-800">
        Model training not executed yet. Train models to view authentic evaluation metrics.
      </div>
    );
  }

  const champion = data.champion_model || 'XGBoost';
  const comparison = data.model_comparison || {};
  const championMetrics = data.champion_metrics || {};
  const cm = championMetrics.confusion_matrix || { tn: 0, fp: 0, fn: 0, tp: 0 };
  const topFeatures = data.top_features || [];

  return (
    <div className="space-y-6">
      {/* Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center space-x-2">
            <BarChart3 className="w-6 h-6 text-cyan-400" />
            <span>Machine Learning Benchmark & Evaluation</span>
          </h1>
          <p className="text-sm text-slate-400">
            Rigorous comparative performance metrics evaluated on held-out test transactions (20% stratified split)
          </p>
        </div>
        <button
          onClick={fetchPerformance}
          className="flex items-center space-x-2 px-3.5 py-2 rounded-xl bg-navy-850 hover:bg-navy-800 border border-navy-700 text-xs font-semibold text-slate-300 self-start sm:self-auto"
        >
          <RefreshCw className="w-3.5 h-3.5 text-cyan-400" />
          <span>Reload Metrics</span>
        </button>
      </div>

      {/* Champion Banner */}
      <div className="p-5 rounded-2xl bg-gradient-to-r from-navy-900 via-navy-850 to-cyan-950/40 border border-cyan-500/30 shadow-2xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center space-x-4">
          <div className="w-12 h-12 rounded-2xl bg-cyan-500/20 text-cyan-400 flex items-center justify-center">
            <Award className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs font-bold uppercase tracking-wider text-cyan-400">
                Champion Model Selected
              </span>
              <span className="px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800 text-[10px] font-mono">
                v{data.version || '1.0.0'}
              </span>
            </div>
            <h2 className="text-xl font-extrabold text-white">{champion} Classifier</h2>
            <p className="text-xs text-slate-400">
              Optimal trade-off balancing high recall (catching fraud) and high precision (preventing false alarms)
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <div className="text-right">
            <span className="text-[10px] uppercase font-bold text-slate-400 block">PR-AUC Score</span>
            <span className="text-2xl font-extrabold text-cyan-400 font-mono">
              {championMetrics.pr_auc ? (championMetrics.pr_auc * 100).toFixed(1) : '—'}%
            </span>
          </div>
          <div className="text-right">
            <span className="text-[10px] uppercase font-bold text-slate-400 block">F1-Score</span>
            <span className="text-2xl font-extrabold text-emerald-400 font-mono">
              {championMetrics.f1_score ? championMetrics.f1_score.toFixed(3) : '—'}
            </span>
          </div>
        </div>
      </div>

      {/* Comparative Model Table */}
      <div className="p-5 rounded-2xl bg-navy-900 border border-navy-800 shadow-xl space-y-4">
        <div>
          <h3 className="font-bold text-white text-base">Algorithm Performance Comparison</h3>
          <p className="text-xs text-slate-400">
            Comparing models under identical stratified test splits and cost-sensitive class weights
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-navy-850 text-slate-400 uppercase font-bold tracking-wider border-b border-navy-800">
              <tr>
                <th className="p-3">Model Algorithm</th>
                <th className="p-3">PR-AUC</th>
                <th className="p-3">ROC-AUC</th>
                <th className="p-3">Precision</th>
                <th className="p-3">Recall</th>
                <th className="p-3">F1-Score</th>
                <th className="p-3">Threshold</th>
                <th className="p-3 text-right">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-800/60">
              {Object.entries(comparison).map(([name, m]) => {
                const isChamp = name === champion;
                return (
                  <tr
                    key={name}
                    className={`transition-colors ${isChamp ? 'bg-cyan-950/20 font-semibold' : 'hover:bg-navy-850/40'}`}
                  >
                    <td className="p-3 flex items-center space-x-2">
                      <span className="text-white font-bold">{name}</span>
                      {isChamp && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-cyan-950 text-cyan-300 border border-cyan-700 font-bold">
                          CHAMPION
                        </span>
                      )}
                    </td>
                    <td className="p-3 font-mono font-bold text-cyan-400">{m.pr_auc.toFixed(4)}</td>
                    <td className="p-3 font-mono text-slate-300">{m.roc_auc.toFixed(4)}</td>
                    <td className="p-3 font-mono text-slate-300">{(m.precision * 100).toFixed(1)}%</td>
                    <td className="p-3 font-mono text-slate-300">{(m.recall * 100).toFixed(1)}%</td>
                    <td className="p-3 font-mono font-bold text-emerald-400">{m.f1_score.toFixed(4)}</td>
                    <td className="p-3 font-mono text-slate-400">{m.optimal_threshold.toFixed(3)}</td>
                    <td className="p-3 text-right">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${isChamp ? 'bg-cyan-500 text-navy-950' : 'bg-navy-800 text-slate-400'}`}>
                        {isChamp ? 'Active' : 'Benchmarked'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Grid: Confusion Matrix & Global Feature Importance */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Confusion Matrix */}
        <div className="lg:col-span-5 p-5 rounded-2xl bg-navy-900 border border-navy-800 shadow-xl space-y-4">
          <div>
            <h3 className="font-bold text-white text-base">Confusion Matrix (Held-out Test Split)</h3>
            <p className="text-xs text-slate-400">Evaluated at optimal threshold {championMetrics.optimal_threshold}</p>
          </div>

          <div className="grid grid-cols-2 gap-3 p-3 bg-navy-950 rounded-xl border border-navy-800 font-mono text-center">
            {/* True Negatives */}
            <div className="p-4 rounded-lg bg-navy-900 border border-emerald-500/30">
              <span className="text-[10px] text-slate-400 block uppercase font-sans">True Negatives (TN)</span>
              <span className="text-xl font-extrabold text-emerald-400">{cm.tn.toLocaleString()}</span>
              <span className="text-[10px] text-slate-500 block mt-1">Legit correctly passed</span>
            </div>

            {/* False Positives */}
            <div className="p-4 rounded-lg bg-navy-900 border border-amber-500/30">
              <span className="text-[10px] text-slate-400 block uppercase font-sans">False Positives (FP)</span>
              <span className="text-xl font-extrabold text-amber-400">{cm.fp.toLocaleString()}</span>
              <span className="text-[10px] text-slate-500 block mt-1">False alarms</span>
            </div>

            {/* False Negatives */}
            <div className="p-4 rounded-lg bg-navy-900 border border-rose-500/30">
              <span className="text-[10px] text-slate-400 block uppercase font-sans">False Negatives (FN)</span>
              <span className="text-xl font-extrabold text-rose-400">{cm.fn.toLocaleString()}</span>
              <span className="text-[10px] text-slate-500 block mt-1">Missed fraud</span>
            </div>

            {/* True Positives */}
            <div className="p-4 rounded-lg bg-navy-900 border border-cyan-500/30">
              <span className="text-[10px] text-slate-400 block uppercase font-sans">True Positives (TP)</span>
              <span className="text-xl font-extrabold text-cyan-400">{cm.tp.toLocaleString()}</span>
              <span className="text-[10px] text-slate-500 block mt-1">Fraud detected</span>
            </div>
          </div>

          <div className="p-3 rounded-xl bg-navy-850 text-xs text-slate-400 leading-relaxed">
            <span className="font-bold text-slate-300 block mb-1">
              Why Accuracy is Never Used in Fraud Detection:
            </span>
            Because only 0.17% of transactions are fraudulent, a naive classifier that predicts everything as legitimate would achieve 99.83% accuracy while catching 0% of fraud. FraudShield AI prioritizes <strong>PR-AUC</strong> and <strong>F1-score</strong>.
          </div>
        </div>

        {/* Global Feature Importance */}
        <div className="lg:col-span-7 p-5 rounded-2xl bg-navy-900 border border-navy-800 shadow-xl space-y-4">
          <div>
            <h3 className="font-bold text-white text-base">Top 10 Global Predictive Features</h3>
            <p className="text-xs text-slate-400">Key PCA features driving fraud classification</p>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                layout="vertical"
                data={topFeatures}
                margin={{ top: 5, right: 30, left: 10, bottom: 5 }}
              >
                <XAxis type="number" stroke="#64748B" fontSize={11} />
                <YAxis type="category" dataKey="feature" stroke="#94A3B8" fontSize={11} width={45} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0A1128', borderColor: '#1E293B', borderRadius: '12px' }}
                />
                <Bar dataKey="importance" fill="#06B6D4" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <p className="text-[11px] text-slate-400 text-center italic">
            *Note: Features V1 through V28 represent orthogonal PCA transformations preserving consumer cardholder privacy.
          </p>
        </div>
      </div>
    </div>
  );
}
