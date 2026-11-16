import React, { useState, useEffect } from 'react';
import { Search, Filter, ChevronLeft, ChevronRight, RefreshCw, Eye } from 'lucide-react';
import RiskBadge from '../components/RiskBadge';
import TransactionModal from '../components/TransactionModal';
import { getTransactions } from '../services/api';

export default function TransactionHistory() {
  const [transactions, setTransactions] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [pageSize] = useState(12);
  const [search, setSearch] = useState('');
  const [riskFilter, setRiskFilter] = useState('');
  const [predictionFilter, setPredictionFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedTxn, setSelectedTxn] = useState(null);

  const fetchTransactions = async () => {
    setLoading(true);
    try {
      const params = {
        page,
        page_size: pageSize,
      };
      if (search.trim()) params.search = search.trim();
      if (riskFilter) params.risk_category = riskFilter;
      if (predictionFilter) params.prediction = predictionFilter;

      const data = await getTransactions(params);
      setTransactions(data.items || []);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch (err) {
      console.error('Error fetching transactions:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTransactions();
  }, [page, riskFilter, predictionFilter]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    fetchTransactions();
  };

  return (
    <div className="space-y-6">
      {/* Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight">
            Transaction Ledger & Audit History
          </h1>
          <p className="text-sm text-slate-400">
            Search, filter, and inspect audited transactions and their SHAP attribution profiles
          </p>
        </div>
        <button
          onClick={fetchTransactions}
          disabled={loading}
          className="flex items-center space-x-2 px-3.5 py-2 rounded-xl bg-navy-850 hover:bg-navy-800 border border-navy-700 text-xs font-semibold text-slate-300 self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="p-4 rounded-2xl bg-navy-900 border border-navy-800 flex flex-col md:flex-row gap-4 items-center justify-between">
        <form onSubmit={handleSearchSubmit} className="relative w-full md:w-80">
          <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by ID (e.g. FS-)"
            className="w-full pl-9 pr-4 py-2 rounded-xl bg-navy-850 border border-navy-700 text-white text-xs placeholder:text-slate-500 focus:outline-none focus:border-cyan-400"
          />
        </form>

        <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
          <div className="flex items-center space-x-2 text-xs text-slate-400">
            <Filter className="w-3.5 h-3.5" />
            <span>Risk:</span>
            <select
              value={riskFilter}
              onChange={(e) => {
                setRiskFilter(e.target.value);
                setPage(1);
              }}
              className="px-3 py-1.5 rounded-lg bg-navy-850 border border-navy-700 text-slate-200 text-xs focus:outline-none focus:border-cyan-400"
            >
              <option value="">All Categories</option>
              <option value="LOW">Low</option>
              <option value="MEDIUM">Medium</option>
              <option value="HIGH">High</option>
            </select>
          </div>

          <div className="flex items-center space-x-2 text-xs text-slate-400">
            <span>Verdict:</span>
            <select
              value={predictionFilter}
              onChange={(e) => {
                setPredictionFilter(e.target.value);
                setPage(1);
              }}
              className="px-3 py-1.5 rounded-lg bg-navy-850 border border-navy-700 text-slate-200 text-xs focus:outline-none focus:border-cyan-400"
            >
              <option value="">All Verdicts</option>
              <option value="LEGITIMATE">Legitimate</option>
              <option value="SUSPICIOUS">Suspicious</option>
            </select>
          </div>
        </div>
      </div>

      {/* Transactions Table */}
      <div className="rounded-2xl bg-navy-900 border border-navy-800 shadow-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-navy-850 text-slate-400 uppercase font-bold tracking-wider border-b border-navy-800">
              <tr>
                <th className="p-3.5">Transaction ID</th>
                <th className="p-3.5">Timestamp</th>
                <th className="p-3.5">Amount</th>
                <th className="p-3.5">Risk Score</th>
                <th className="p-3.5">Fraud Prob</th>
                <th className="p-3.5">Category</th>
                <th className="p-3.5">Verdict</th>
                <th className="p-3.5 text-right">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-800/60">
              {transactions.length > 0 ? (
                transactions.map((txn) => {
                  const isSuspicious = txn.prediction === 'SUSPICIOUS';
                  return (
                    <tr
                      key={txn.transaction_id}
                      onClick={() => setSelectedTxn(txn)}
                      className="hover:bg-navy-850/60 cursor-pointer transition-colors"
                    >
                      <td className="p-3.5 font-mono font-bold text-cyan-300">
                        {txn.transaction_id}
                      </td>
                      <td className="p-3.5 text-slate-400 whitespace-nowrap">
                        {new Date(txn.timestamp).toLocaleString()}
                      </td>
                      <td className="p-3.5 font-medium text-white font-mono">
                        ${Number(txn.amount).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="p-3.5 font-mono font-bold text-slate-200">
                        {txn.risk_score}
                      </td>
                      <td className="p-3.5 font-mono text-cyan-400">
                        {(txn.fraud_probability * 100).toFixed(1)}%
                      </td>
                      <td className="p-3.5">
                        <RiskBadge category={txn.risk_category} showIcon={false} />
                      </td>
                      <td className="p-3.5">
                        <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold ${isSuspicious ? 'bg-rose-950 text-rose-300 border border-rose-600/40' : 'bg-emerald-950 text-emerald-300 border border-emerald-600/40'}`}>
                          {txn.prediction}
                        </span>
                      </td>
                      <td className="p-3.5 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedTxn(txn);
                          }}
                          className="p-1 rounded hover:bg-navy-800 text-slate-400 hover:text-cyan-400 transition-colors"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan="8" className="p-8 text-center text-slate-500">
                    No matching transactions found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        <div className="p-4 border-t border-navy-800 bg-navy-850 flex items-center justify-between text-xs text-slate-400">
          <span>
            Showing page <strong className="text-white">{page}</strong> of <strong className="text-white">{totalPages}</strong> ({total} total records)
          </span>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="p-1.5 rounded-lg bg-navy-900 border border-navy-700 text-slate-300 disabled:opacity-40 hover:bg-navy-800"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="p-1.5 rounded-lg bg-navy-900 border border-navy-700 text-slate-300 disabled:opacity-40 hover:bg-navy-800"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Modal */}
      {selectedTxn && (
        <TransactionModal
          transaction={selectedTxn}
          onClose={() => setSelectedTxn(null)}
        />
      )}
    </div>
  );
}
