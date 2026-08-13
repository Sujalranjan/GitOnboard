import React from 'react';

export function Card({ children, className = '', noPadding = false }) {
  return (
    <div className={`bg-white dark:bg-slate-900 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 transition-colors ${className}`}>
      {!noPadding ? <div className="p-6">{children}</div> : children}
    </div>
  );
}

/**
 * @param {Object} props
 * @param {string} props.title
 * @param {string|React.ReactNode} [props.subtitle]
 * @param {React.ReactNode} [props.action]
 * @param {string} [props.className]
 */
export function CardHeader({ title, subtitle, action, className = '' }) {
  return (
    <div className={`flex items-center justify-between border-b border-slate-100 dark:border-slate-800 px-6 py-4 bg-slate-50/50 dark:bg-slate-800/50 ${className}`}>
      <div>
        <h3 className="font-semibold text-slate-800 dark:text-slate-200">{title}</h3>
        {subtitle && <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{subtitle}</p>}
      </div>
      {action && <div>{action}</div>}
    </div>
  );
}
