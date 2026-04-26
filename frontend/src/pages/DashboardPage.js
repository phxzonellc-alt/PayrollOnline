import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { Button } from '../components/ui/button';
import { toast } from 'sonner';
import { LogOut, Users, FileSpreadsheet, ArrowLeft, BarChart3 } from 'lucide-react';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend,
} from 'recharts';

const $f = (n) => `$${(Number(n) || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const numF = (n) => (Number(n) || 0).toLocaleString('en-US', { maximumFractionDigits: 1 });

function KpiCard({ label, value, sub, testId }) {
  return (
    <div data-testid={testId} className="border border-border p-5 bg-background hover:border-primary/40 transition-colors duration-200">
      <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">{label}</p>
      <p className="font-heading text-3xl font-black tracking-tight mt-2">{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const isAdmin = user?.role === 'admin';

  const load = useCallback(async () => {
    try {
      const res = await api.get('/analytics/dashboard');
      setData(res.data);
    } catch { toast.error('Failed to load analytics'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleExport = async () => {
    try {
      const res = await api.get('/analytics/export/excel', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'payroll_analytics.xlsx';
      a.click();
      window.URL.revokeObjectURL(url);
      toast.success('Analytics exported');
    } catch { toast.error('Export failed'); }
  };

  const handleEmployeeReport = async () => {
    try {
      const res = await api.get('/analytics/employee-report/excel', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'employee_report.xlsx';
      a.click();
      window.URL.revokeObjectURL(url);
      toast.success('Employee report exported');
    } catch { toast.error('Export failed'); }
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-3 flex items-center justify-between sticky top-0 bg-background z-50">
        <div className="flex items-center gap-4">
          <h1 className="font-heading text-2xl font-black tracking-tight">MEBO</h1>
          <span className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Analytics</span>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate('/')} data-testid="back-to-events-button" className="rounded-sm gap-2 text-xs">
            <ArrowLeft className="h-4 w-4" /> Events
          </Button>
          {isAdmin && (
            <Button variant="ghost" size="sm" onClick={() => navigate('/users')} data-testid="manage-users-button" className="rounded-sm gap-2 text-xs">
              <Users className="h-4 w-4" /> Users
            </Button>
          )}
          <span className="text-sm text-muted-foreground">{user?.email}</span>
          <span className="text-[10px] uppercase tracking-wider font-semibold border border-border rounded-sm px-1.5 py-0.5 text-muted-foreground">{user?.role}</span>
          <Button variant="ghost" size="sm" onClick={logout} data-testid="logout-button" className="rounded-sm">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </header>

      <main className="p-6 max-w-7xl mx-auto" data-testid="dashboard-page">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="font-heading text-2xl font-bold tracking-tight">Dashboard</h2>
            <p className="text-xs text-muted-foreground mt-1">Cross-event totals and trends. Updates as you enter hours.</p>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={handleExport} data-testid="export-analytics-excel-button" className="rounded-sm gap-2" variant="outline">
              <FileSpreadsheet className="h-4 w-4" /> Dashboard Excel
            </Button>
            <Button onClick={handleEmployeeReport} data-testid="export-employee-report-button" className="rounded-sm gap-2">
              <FileSpreadsheet className="h-4 w-4" /> Employee Report
            </Button>
          </div>
        </div>

        {loading ? (
          <p className="text-muted-foreground text-sm">Loading analytics...</p>
        ) : !data ? (
          <p className="text-muted-foreground text-sm">No data available.</p>
        ) : data.totals.events === 0 ? (
          <div className="border border-dashed border-border p-12 text-center">
            <BarChart3 className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground text-sm">No events yet. Create your first event to start seeing analytics.</p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6" data-testid="kpi-grid">
              <KpiCard testId="kpi-gross" label="Gross Payroll" value={$f(data.totals.gross)} sub="All events" />
              <KpiCard testId="kpi-benefits" label="Benefits" value={$f(data.totals.benefit_co)} />
              <KpiCard testId="kpi-fund" label="Fund Contributions" value={$f(data.totals.fund_co)} />
              <KpiCard testId="kpi-deductions" label="Deductions" value={$f(data.totals.deduction)} />
              <KpiCard testId="kpi-hours" label="Hours Worked" value={numF(data.totals.total_hours)} />
              <KpiCard testId="kpi-employees" label="Active Employees" value={numF(data.totals.active_employees)} sub="With hours entered" />
              <KpiCard testId="kpi-events" label="Events" value={numF(data.totals.events)} />
              <KpiCard
                testId="kpi-grand-total"
                label="Grand Total"
                value={$f(data.totals.gross + data.totals.benefit_co + data.totals.fund_co + data.totals.deduction)}
                sub="Gross + Benefits + Fund + Deductions"
              />
            </div>

            <section className="mb-6">
              <p className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-3">Monthly Trend</p>
              <div className="border border-border p-4 bg-background" style={{ height: 320 }} data-testid="monthly-chart">
                {data.monthly.length === 0 ? (
                  <p className="text-muted-foreground text-sm flex items-center justify-center h-full">No monthly data yet.</p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data.monthly} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="2 4" stroke="hsl(var(--border))" />
                      <XAxis dataKey="month" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                      <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                      <Tooltip
                        formatter={(v, name) => [name === 'hours' ? numF(v) : $f(v), name]}
                        contentStyle={{ background: 'hsl(var(--background))', border: '1px solid hsl(var(--border))', borderRadius: 0, fontSize: 12 }}
                      />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Bar dataKey="gross" name="Gross" fill="hsl(var(--primary))" />
                      <Bar dataKey="benefit_co" name="Benefits" fill="#94a3b8" />
                      <Bar dataKey="fund_co" name="Fund" fill="#cbd5e1" />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </section>

            <section className="mb-6">
              <p className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-3">By Employer</p>
              <div className="border border-border overflow-x-auto" data-testid="employer-table">
                <table className="payroll-table w-full border-collapse">
                  <thead>
                    <tr>
                      <th className="text-left">Employer</th>
                      <th>Events</th>
                      <th>Hours</th>
                      <th>Gross</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.employers.length === 0 ? (
                      <tr><td colSpan={4} className="text-center text-muted-foreground text-sm py-6">No employer data yet.</td></tr>
                    ) : data.employers.map((e, i) => (
                      <tr key={e.employer} className={i % 2 === 0 ? '' : 'bg-muted/30'}>
                        <td className="text-sm font-medium">{e.employer}</td>
                        <td className="font-mono text-xs text-right">{e.event_count}</td>
                        <td className="font-mono text-xs text-right">{numF(e.hours)}</td>
                        <td className="font-mono text-xs text-right font-bold">{$f(e.gross)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <p className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-3">Recent Events</p>
              <div className="border border-border divide-y divide-border" data-testid="recent-events-list">
                {data.recent_events.length === 0 ? (
                  <p className="text-muted-foreground text-sm p-4">No events yet.</p>
                ) : data.recent_events.map((ev) => (
                  <div
                    key={ev.id}
                    onClick={() => navigate(`/events/${ev.id}`)}
                    className="flex items-center justify-between px-4 py-3 hover:bg-muted cursor-pointer transition-colors duration-200"
                    data-testid={`recent-event-${ev.id}`}
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 bg-primary/10 flex items-center justify-center rounded-sm">
                        <FileSpreadsheet className="h-4 w-4 text-primary" />
                      </div>
                      <div>
                        <p className="font-semibold text-sm">{ev.event_name || 'Untitled Event'}</p>
                        <p className="text-xs text-muted-foreground">
                          {[ev.job_number && `#${ev.job_number}`, ev.employer].filter(Boolean).join(' / ')}
                        </p>
                      </div>
                    </div>
                    <span className="text-[10px] tracking-wider uppercase text-muted-foreground font-mono">
                      {ev.created_at ? ev.created_at.slice(0, 10) : ''}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
