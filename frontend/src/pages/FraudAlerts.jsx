import React, { useState, useEffect } from 'react';
import { 
  AlertTriangle, 
  CheckCircle, 
  Clock, 
  ShieldAlert, 
  Filter, 
  RefreshCw,
  Edit3
} from 'lucide-react';
import { getAlerts, updateAlertStatus } from '../services/api';

export default function FraudAlerts({ user, onRequireAuth }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [newStatus, setNewStatus] = useState('INVESTIGATING');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchAlerts = async () => {
    setLoading(true);
    try {
      const data = await getAlerts(statusFilter || null);
      setAlerts(data);
    } catch (err) {
      console.error('Error fetching alerts:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
  }, [statusFilter]);

  const handleOpenUpdate = (alert) => {
    if (!user) {
      onRequireAuth();
      return;
    }
    setSelectedAlert(alert);
    setNewStatus(alert.status);
    setNotes(alert.notes || '');
  };

  const handleSaveStatus = async (e) => {
    e.preventDefault();
    if (!selectedAlert) return;
    setSubmitting(true);
    try {
      await updateAlertStatus(selectedAlert.id, {
        status: newStatus,
        notes: notes,
      });
      setSelectedAlert(null);
      fetchAlerts();
    } catch (err) {
      console.error('Failed to update alert:', err);
      alert('Failed to update alert status. Verify login session.');
    } finally {
      setSubmitting(false);
    }
  };

  const getStatusBadge = (st) => {
    switch (st) {
      case 'PENDING':
        return 'bg-rose-950 text-rose-300 border-rose-800';
      case 'INVESTIGATING':
        return 'bg-amber-950 text-amber-300 border-amber-800';
      case 'RESOLVED':
        return 'bg-emerald-950 text-emerald-300 border-emerald-800';
      case 'FALSE_POSITIVE':
        return 'bg-slate-800 text-slate-300 border-slate-700';
      default:
        return 'bg-navy-800 text-slate-400 border-navy-700';
    }
  };

  return (
    <div className="space-y-6">
      {/* Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center space-x-2">
            <AlertTriangle className="w-6 h-6 text-rose-500" />
            <span>Fraud Incident Command & Alerts</span>
          </h1>
          <p className="text-sm text-slate-400">
            Investigate, review, and acknowledge high-risk transactions flagged by the hybrid engine
          </p>
        </div>
        <button
          onClick={fetchAlerts}
          disabled={loading}
          className="flex items-center space-x-2 px-3.5 py-2 rounded-xl bg-navy-850 hover:bg-navy-800 border border-navy-700 text-xs font-semibold text-slate-300 transition-colors self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
          <span>Refresh Alerts</span>
        </button>
      </div>

      {/* Filter Bar */}
      <div className="p-4 rounded-2xl bg-navy-900 border border-navy-800 flex items-center justify-between">
        <div className="flex items-center space-x-3 text-xs">
          <Filter className="w-4 h-4 text-slate-400" />
          <span className="text-slate-400 font-semibold">Filter by Status:</span>
          <div className="flex flex-wrap gap-2">
            {['', 'PENDING', 'INVESTIGATING', 'RESOLVED', 'FALSE_POSITIVE'].map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${
                  statusFilter === st
                    ? 'bg-cyan-500 text-navy-950 font-bold'
                    : 'bg-navy-850 text-slate-400 hover:text-white'
                }`}
              >
                {st === '' ? 'All Alerts' : st}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Alerts Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {alerts.length > 0 ? (
          alerts.map((alert) => (
            <div
              key={alert.id}
              className="p-5 rounded-2xl bg-navy-900 border border-navy-800 shadow-xl flex flex-col justify-between space-y-4 hover:border-navy-700 transition-all"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-xs font-bold text-cyan-300">
                    {alert.transaction_id}
                  </span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold border ${getStatusBadge(alert.status)}`}>
                    {alert.status}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 my-3 p-2.5 rounded-xl bg-navy-850 border border-navy-800 text-xs">
                  <div>
                    <span className="text-[10px] text-slate-400 block uppercase">Risk Score</span>
                    <span className="font-bold text-rose-400 font-mono text-base">{alert.risk_score}</span>
                    <span className="text-slate-500 text-[10px]"> / 100</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block uppercase">Probability</span>
                    <span className="font-bold text-cyan-300 font-mono text-base">
                      {(alert.fraud_probability * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>

                <p className="text-xs text-slate-300 line-clamp-2">
                  {alert.notes || 'Automated anomaly detection alert.'}
                </p>
              </div>

              <div className="pt-3 border-t border-navy-800 flex items-center justify-between text-[11px] text-slate-400">
                <span>{new Date(alert.created_at).toLocaleDateString()}</span>
                <button
                  onClick={() => handleOpenUpdate(alert)}
                  className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-navy-800 hover:bg-navy-700 text-slate-200 font-semibold transition-colors"
                >
                  <Edit3 className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Update Status</span>
                </button>
              </div>
            </div>
          ))
        ) : (
          <div className="col-span-full p-12 text-center text-slate-500 bg-navy-900 rounded-2xl border border-navy-800">
            No active alerts matching current filter.
          </div>
        )}
      </div>

      {/* Acknowledge / Update Modal */}
      {selectedAlert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/80 backdrop-blur-sm animate-fadeIn">
          <form
            onSubmit={handleSaveStatus}
            className="w-full max-w-md p-6 rounded-2xl bg-navy-900 border border-navy-700 shadow-2xl space-y-4"
          >
            <h3 className="font-bold text-white text-base">
              Update Alert #{selectedAlert.id} ({selectedAlert.transaction_id})
            </h3>

            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1">
                Investigation Status
              </label>
              <select
                value={newStatus}
                onChange={(e) => setNewStatus(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-navy-850 border border-navy-700 text-slate-200 text-sm focus:outline-none focus:border-cyan-400"
              >
                <option value="PENDING">Pending Review</option>
                <option value="INVESTIGATING">Under Investigation</option>
                <option value="RESOLVED">Confirmed Fraud (Resolved)</option>
                <option value="FALSE_POSITIVE">False Positive (Dismissed)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-400 mb-1">
                Investigation Notes
              </label>
              <textarea
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Document verification steps or cardholder confirmation..."
                className="w-full px-3 py-2 rounded-xl bg-navy-850 border border-navy-700 text-white text-xs focus:outline-none focus:border-cyan-400"
              />
            </div>

            <div className="flex items-center justify-end space-x-2 pt-2">
              <button
                type="button"
                onClick={() => setSelectedAlert(null)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-navy-950 font-bold text-xs"
              >
                {submitting ? 'Updating...' : 'Save Resolution'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
