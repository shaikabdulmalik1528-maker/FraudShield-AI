import React, { useState, useEffect } from 'react';
import { 
  ShieldAlert, 
  ShieldCheck, 
  Activity, 
  TrendingUp, 
  DollarSign, 
  AlertTriangle,
  RefreshCw
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell
} from 'recharts';
import StatCard from '../components/StatCard';
import RiskBadge from '../components/RiskBadge';
import TransactionModal from '../components/TransactionModal';
import { getOverviewStats, getFraudTrends, getRiskDistribution, getTransactions } from '../services/api';

export default function Dashboard({ onNavigateToAnalysis }) {
  const [stats, setStats] = useState(null);
  const [trends, setTrends] = useState([]);
  const [riskDist, setRiskDist] = useState([]);
  const [recentTxns, setRecentTxns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTxn, setSelectedTxn] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [overviewData, trendsData, distData, txnsData] = await Promise.all([
        getOverviewStats(),
        getFraudTrends(),
        getRiskDistribution(),
        getTransactions({ page: 1, page_size: 7 }),
      ]);
      setStats(overviewData);
      setTrends(trendsData);
      setRiskDist(distData);
      setRecentTxns(txnsData.items || []);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const PIE_COLORS = {
    LOW: '#10B981',
    MEDIUM: '#F59E0B',
    HIGH: '#F43F5E',
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight">
            Executive Fraud Intelligence
          </h1>
          <p className="text-sm text-slate-400">
            Real-time transaction risk scoring and anomaly detection metrics
          </p>
        </div>
        <div className="flex items-center space-x-3">
          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center space-x-2 px-3.5 py-2 rounded-xl bg-navy-850 hover:bg-navy-800 border border-navy-700/60 text-xs font-semibold text-slate-300 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
            <span>Refresh Data</span>
          </button>
          <button
            onClick={onNavigateToAnalysis}
            className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-600 to-cyan-500 hover:from-cyan-500 hover:to-cyan-400 text-navy-950 font-bold text-xs shadow-lg shadow-cyan-500/20 transition-all"
          >
            <span>Scan Transaction</span>
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Transactions"
          value={stats ? stats.total_transactions.toLocaleString() : '—'}
          subtitle="Processed in current pipeline"
          icon={Activity}
          color="cyan"
        />
        <StatCard
          title="Fraudulent Flagged"
          value={stats ? stats.fraudulent_transactions.toLocaleString() : '—'}
          subtitle={stats ? `${stats.fraud_rate_pct}% of total volume` : '—'}
          icon={ShieldAlert}
          color="rose"
        />
        <StatCard
          title="Legitimate Volume"
          value={stats ? stats.legitimate_transactions.toLocaleString() : '—'}
          subtitle={stats ? `$${stats.total_volume_usd.toLocaleString()}` : '—'}
          icon={ShieldCheck}
          color="emerald"
        />
        <StatCard
          title="Average Risk Score"
          value={stats ? `${stats.average_risk_score} / 100` : '—'}
          subtitle={stats ? `${stats.open_alerts} open fraud alerts` : '—'}
          icon={AlertTriangle}
          color="amber"
        />
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Fraud Trends Area Chart */}
        <div className="lg:col-span-2 p-5 rounded-2xl bg-navy-900 border border-navy-800 shadow-xl space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold text-white text-base">Transaction & Fraud Activity</h3>
              <p className="text-xs text-slate-400">Total requests and flagged fraud events</p>
            </div>
            <div className="flex items-center space-x-4 text-xs">
              <span className="flex items-center space-x-1.5 text-slate-300">
                <span className="w-2.5 h-2.5 rounded-full bg-cyan-400"></span>
                <span>Total</span>
              </span>
              <span className="flex items-center space-x-1.5 text-slate-300">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
                <span>Fraud</span>
              </span>
            </div>
          </div>

          <div className="h-64 w-full">
            {trends.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trends} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="totalGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#06B6D4" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#06B6D4" stopOpacity={0.0} />
                    </linearGradient>
                    <linearGradient id="fraudGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#F43F5E" stopOpacity={0.6} />
                      <stop offset="95%" stopColor="#F43F5E" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date_or_hour" stroke="#64748B" fontSize={11} tickFormatter={(v) => v.slice(11, 16)} />
                  <YAxis stroke="#64748B" fontSize={11} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#0A1128', borderColor: '#1E293B', borderRadius: '12px' }}
                    labelStyle={{ color: '#F8FAFC', fontWeight: 'bold' }}
                  />
                  <Area type="monotone" dataKey="total_count" stroke="#06B6D4" strokeWidth={2} fillOpacity={1} fill="url(#totalGrad)" name="Total Transactions" />
                  <Area type="monotone" dataKey="fraud_count" stroke="#F43F5E" strokeWidth={2} fillOpacity={1} fill="url(#fraudGrad)" name="Fraud Detections" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500 text-xs">
                No activity data available yet.
              </div>
            )}
          </div>
        </div>

        {/* Risk Breakdown Donut */}
        <div className="p-5 rounded-2xl bg-navy-900 border border-navy-800 shadow-xl space-y-4 flex flex-col justify-between">
          <div>
            <h3 className="font-bold text-white text-base">Risk Distribution</h3>
            <p className="text-xs text-slate-400">Classified transactions by risk category</p>
          </div>

          <div className="h-48 w-full flex items-center justify-center">
            {riskDist.some((d) => d.count > 0) ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={riskDist}
                    dataKey="count"
                    nameKey="category"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={75}
                    paddingAngle={4}
                  >
                    {riskDist.map((entry) => (
                      <Cell key={entry.category} fill={PIE_COLORS[entry.category] || '#64748B'} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: '#0A1128', borderColor: '#1E293B', borderRadius: '12px' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-slate-500 text-xs">No risk distributions calculated yet.</div>
            )}
          </div>

          <div className="grid grid-cols-3 gap-2 text-center">
            {riskDist.map((item) => (
              <div key={item.category} className="p-2 rounded-xl bg-navy-850 border border-navy-800">
                <span className="text-[10px] font-bold text-slate-400 block">{item.category}</span>
                <span className="text-sm font-bold text-white">{item.percentage}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recent Transactions Table */}
      <div className="p-5 rounded-2xl bg-navy-900 border border-navy-800 shadow-xl space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-bold text-white text-base">Recent Real-Time Transactions</h3>
            <p className="text-xs text-slate-400">Latest records processed by the hybrid risk engine</p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-navy-850 text-slate-400 uppercase font-bold tracking-wider border-b border-navy-800">
              <tr>
                <th className="p-3">Transaction ID</th>
                <th className="p-3">Amount</th>
                <th className="p-3">Risk Score</th>
                <th className="p-3">Category</th>
                <th className="p-3">Anomaly</th>
                <th className="p-3">Verdict</th>
                <th className="p-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-800/60">
              {recentTxns.length > 0 ? (
                recentTxns.map((txn) => {
                  const isSuspicious = txn.prediction === 'SUSPICIOUS';
                  return (
                    <tr key={txn.transaction_id} className="hover:bg-navy-850/50 transition-colors">
                      <td className="p-3 font-mono font-bold text-cyan-300">{txn.transaction_id}</td>
                      <td className="p-3 font-medium text-white">
                        ${Number(txn.amount).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="p-3">
                        <span className="font-mono font-bold text-slate-200">{txn.risk_score}</span>
                        <span className="text-slate-500 text-[10px]"> / 100</span>
                      </td>
                      <td className="p-3">
                        <RiskBadge category={txn.risk_category} showIcon={false} />
                      </td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${txn.is_anomaly ? 'bg-amber-950 text-amber-300 border border-amber-800' : 'text-slate-400'}`}>
                          {txn.is_anomaly ? 'Outlier' : 'Normal'}
                        </span>
                      </td>
                      <td className="p-3">
                        <span className={`px-2.5 py-1 rounded-full text-[11px] font-extrabold ${isSuspicious ? 'bg-rose-950/80 text-rose-300 border border-rose-500/40' : 'bg-emerald-950/80 text-emerald-300 border border-emerald-500/40'}`}>
                          {txn.prediction}
                        </span>
                      </td>
                      <td className="p-3 text-right">
                        <button
                          onClick={() => setSelectedTxn(txn)}
                          className="px-2.5 py-1 rounded bg-navy-800 hover:bg-navy-700 text-slate-300 text-[11px] font-medium transition-colors"
                        >
                          Inspect SHAP
                        </button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan="7" className="p-6 text-center text-slate-500">
                    No recent transactions found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Transaction Detail Modal */}
      {selectedTxn && (
        <TransactionModal
          transaction={selectedTxn}
          onClose={() => setSelectedTxn(null)}
        />
      )}
    </div>
  );
}
