import React, { useState } from 'react';
import { X, ShieldAlert, ShieldCheck, Activity, Cpu, ChevronDown, ChevronUp } from 'lucide-react';
import RiskBadge from './RiskBadge';
import ShapChart from './ShapChart';

export default function TransactionModal({ transaction, onClose }) {
  const [showRawFeatures, setShowRawFeatures] = useState(false);

  if (!transaction) return null;

  const isSuspicious = transaction.prediction === 'SUSPICIOUS';
  const explanation = transaction.explanation;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/80 backdrop-blur-sm animate-fadeIn">
      <div className="relative w-full max-w-3xl max-h-[90vh] overflow-y-auto bg-navy-900 border border-navy-700 rounded-2xl shadow-2xl">
        {/* Header */}
        <div className="sticky top-0 bg-navy-900/95 backdrop-blur-md p-5 border-b border-navy-800 flex items-center justify-between z-10">
          <div className="flex items-center space-x-3">
            <div className={`p-2 rounded-xl ${isSuspicious ? 'bg-rose-500/20 text-rose-400' : 'bg-emerald-500/20 text-emerald-400'}`}>
              {isSuspicious ? <ShieldAlert className="w-5 h-5" /> : <ShieldCheck className="w-5 h-5" />}
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="font-bold text-white text-base">{transaction.transaction_id}</h3>
                <RiskBadge category={transaction.risk_category} score={transaction.risk_score} />
              </div>
              <p className="text-xs text-slate-400">
                Processed at {new Date(transaction.timestamp).toLocaleString()}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-navy-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-6">
          {/* Key Metrics Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 rounded-xl bg-navy-850 border border-navy-800">
              <span className="text-[10px] text-slate-400 font-bold uppercase">Amount</span>
              <p className="text-lg font-bold text-white mt-1">
                ${Number(transaction.amount).toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </p>
            </div>
            <div className="p-3 rounded-xl bg-navy-850 border border-navy-800">
              <span className="text-[10px] text-slate-400 font-bold uppercase">Fraud Probability</span>
              <p className="text-lg font-bold text-cyan-400 mt-1">
                {(transaction.fraud_probability * 100).toFixed(1)}%
              </p>
            </div>
            <div className="p-3 rounded-xl bg-navy-850 border border-navy-800">
              <span className="text-[10px] text-slate-400 font-bold uppercase">Anomaly Outlier</span>
              <p className={`text-lg font-bold mt-1 ${transaction.is_anomaly ? 'text-amber-400' : 'text-slate-300'}`}>
                {transaction.is_anomaly ? 'Detected' : 'Normal'}
              </p>
            </div>
            <div className="p-3 rounded-xl bg-navy-850 border border-navy-800">
              <span className="text-[10px] text-slate-400 font-bold uppercase">Verdict</span>
              <p className={`text-lg font-bold mt-1 ${isSuspicious ? 'text-rose-400' : 'text-emerald-400'}`}>
                {transaction.prediction}
              </p>
            </div>
          </div>

          {/* Explainability Section */}
          <div>
            <h4 className="text-sm font-bold text-slate-200 mb-3 flex items-center space-x-2">
              <Cpu className="w-4 h-4 text-cyan-400" />
              <span>SHAP Explainability & Risk Attribution</span>
            </h4>
            {explanation ? (
              <ShapChart
                topFeatures={explanation.top_features}
                summary={explanation.summary}
              />
            ) : (
              <p className="text-xs text-slate-400 p-4 bg-navy-850 rounded-xl">
                No explanation stored for this record.
              </p>
            )}
          </div>

          {/* Raw PCA Feature Breakdown (Collapsible) */}
          {transaction.features && (
            <div className="border border-navy-800 rounded-xl overflow-hidden">
              <button
                onClick={() => setShowRawFeatures(!showRawFeatures)}
                className="w-full p-3.5 bg-navy-850 flex items-center justify-between text-xs font-semibold text-slate-300 hover:text-white"
              >
                <span>Raw PCA Features (V1 to V28)</span>
                {showRawFeatures ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>

              {showRawFeatures && (
                <div className="p-4 bg-navy-950 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
                  {Object.entries(transaction.features).map(([key, val]) => (
                    <div key={key} className="p-1.5 rounded bg-navy-900 border border-navy-800 flex justify-between">
                      <span className="text-slate-400">{key}:</span>
                      <span className={val < 0 ? 'text-cyan-400' : 'text-slate-200'}>
                        {Number(val).toFixed(3)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
