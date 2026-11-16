import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell
} from 'recharts';

export default function ShapChart({ topFeatures = [], summary = '' }) {
  if (!topFeatures || topFeatures.length === 0) {
    return (
      <div className="p-6 text-center text-slate-400 text-xs bg-navy-900 rounded-xl border border-navy-800">
        No feature explanation data available.
      </div>
    );
  }

  // Format data for Recharts horizontal bar chart
  const data = [...topFeatures].reverse().map((item) => ({
    name: item.feature,
    value: item.shap_value,
    impactPct: item.impact_pct,
    rawVal: item.feature_value,
    direction: item.contribution,
    description: item.description,
  }));

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const d = payload[0].payload;
      return (
        <div className="p-3 bg-navy-900 border border-navy-700 rounded-xl shadow-2xl text-xs space-y-1">
          <p className="font-bold text-white">{d.name}</p>
          <p className="text-slate-300">
            Observed Value: <span className="font-mono text-cyan-400">{d.rawVal}</span>
          </p>
          <p className="text-slate-300">
            SHAP Value: <span className={`font-mono font-bold ${d.value > 0 ? 'text-rose-400' : 'text-cyan-400'}`}>
              {d.value > 0 ? `+${d.value}` : d.value}
            </span>
          </p>
          <p className="text-[11px] text-slate-400 max-w-xs">{d.description}</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-4">
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            layout="vertical"
            data={data}
            margin={{ top: 10, right: 30, left: 20, bottom: 5 }}
          >
            <XAxis
              type="number"
              stroke="#64748B"
              fontSize={11}
              tickFormatter={(v) => `${v > 0 ? '+' : ''}${v.toFixed(2)}`}
            />
            <YAxis
              type="category"
              dataKey="name"
              stroke="#94A3B8"
              fontSize={12}
              width={50}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine x={0} stroke="#475569" strokeDasharray="3 3" />
            <Bar dataKey="value" radius={[4, 4, 4, 4]}>
              {data.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.value > 0 ? '#F43F5E' : '#06B6D4'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {summary && (
        <div className="p-3.5 rounded-xl bg-navy-850 border border-navy-700/60 text-xs text-slate-300 leading-relaxed">
          <span className="font-bold text-cyan-400 uppercase tracking-wide text-[10px] block mb-1">
            SHAP AI Explanation Summary
          </span>
          {summary}
        </div>
      )}
    </div>
  );
}
