import { useMemo } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { calcGross, $f, HOUR_FIELDS } from '../../lib/payroll';
import { Save, Eye, Edit3, Printer, Search, X } from 'lucide-react';

function DailyStatement({ dailyStatement, dayNum }) {
  const emps = useMemo(() => dailyStatement?.employees || [], [dailyStatement?.employees]);
  const activeEmps = useMemo(() => emps.filter(e => e.total_hours > 0 || e.sr_hours > 0), [emps]);

  const totals = useMemo(() => ({
    st: activeEmps.reduce((s, e) => s + e.st_hrs, 0),
    ot: activeEmps.reduce((s, e) => s + e.ot_hrs, 0),
    dt: activeEmps.reduce((s, e) => s + e.dt_hrs, 0),
    sr: activeEmps.reduce((s, e) => s + e.sr_hours, 0),
    specialTot: activeEmps.reduce((s, e) => s + e.special_tot, 0),
    totalHrs: activeEmps.reduce((s, e) => s + e.total_hours, 0),
    benefit: activeEmps.reduce((s, e) => s + e.benefit_co, 0),
    fund: activeEmps.reduce((s, e) => s + e.fund_co, 0),
    deduction: activeEmps.reduce((s, e) => s + e.deduction, 0),
    gross: activeEmps.reduce((s, e) => s + e.gross, 0),
  }), [activeEmps]);

  if (!dailyStatement || dailyStatement.day !== dayNum) {
    return <p className="text-muted-foreground text-sm p-4">Loading statement...</p>;
  }

  const stFp = dailyStatement.fund_pct;
  const stBp = dailyStatement.benefit_pct;
  const stDp = dailyStatement.deduction_pct;

  return (
    <div className="overflow-x-auto border border-border">
      <table className="payroll-table w-full border-collapse">
        <thead>
          <tr>
            <th className="text-left w-10">#</th>
            <th className="text-left">Employee</th>
            <th className="text-left">Dept/Emp #</th>
            <th className="text-right">Hrly Rate</th>
            <th className="text-right">S.T. Hrs</th>
            <th className="text-right">O.T. Hrs</th>
            <th className="text-right">D.T. Hrs</th>
            <th className="text-right">Special Rate</th>
            <th className="text-right">SR Hrs</th>
            <th className="text-right">Special Tot</th>
            <th className="text-right">Total Hours</th>
            <th className="text-right">Benefit ({(stBp * 100).toFixed(0)}%)</th>
            <th className="text-right">Fund ({(stFp * 100).toFixed(0)}%)</th>
            <th className="text-right">Deduct ({(stDp * 100).toFixed(0)}%)</th>
            <th className="text-right">Gross Salary</th>
          </tr>
        </thead>
        <tbody>
          {activeEmps.map((emp, i) => {
            const r2c = emp.used_r2 ? ' r2-col' : '';
            return (
              <tr key={emp.employee_id} className={i % 2 === 0 ? '' : 'bg-muted/30'}>
                <td className="font-mono text-xs text-muted-foreground">{i + 1}</td>
                <td className="text-sm font-medium">{emp.name}</td>
                <td className="text-xs text-muted-foreground">{emp.dept_emp_num}</td>
                <td className={`font-mono text-xs text-right${r2c}`}>{$f(emp.hrly_rate)}</td>
                <td className={`font-mono text-xs text-right${r2c}`}>{emp.st_hrs > 0 ? emp.st_hrs.toFixed(1) : '-'}</td>
                <td className={`font-mono text-xs text-right${r2c}`}>{emp.ot_hrs > 0 ? emp.ot_hrs.toFixed(1) : '-'}</td>
                <td className={`font-mono text-xs text-right${r2c}`}>{emp.dt_hrs > 0 ? emp.dt_hrs.toFixed(1) : '-'}</td>
                <td className="font-mono text-xs text-right">{emp.special_rate > 0 ? $f(emp.special_rate) : '-'}</td>
                <td className="font-mono text-xs text-right">{emp.sr_hours > 0 ? emp.sr_hours.toFixed(1) : '-'}</td>
                <td className="font-mono text-xs text-right">{emp.special_tot > 0 ? $f(emp.special_tot) : '-'}</td>
                <td className="font-mono text-xs text-right font-semibold">{emp.total_hours.toFixed(1)}</td>
                <td className="font-mono text-xs text-right">{$f(emp.benefit_co)}</td>
                <td className="font-mono text-xs text-right">{$f(emp.fund_co)}</td>
                <td className="font-mono text-xs text-right">{$f(emp.deduction)}</td>
                <td className="font-mono text-xs text-right font-bold">{$f(emp.gross)}</td>
              </tr>
            );
          })}
          {activeEmps.length > 0 && (
            <tr className="total-row">
              <td></td><td className="font-semibold">TOTALS</td><td></td><td></td>
              <td className="font-mono text-xs text-right font-bold">{totals.st.toFixed(1)}</td>
              <td className="font-mono text-xs text-right font-bold">{totals.ot.toFixed(1)}</td>
              <td className="font-mono text-xs text-right font-bold">{totals.dt.toFixed(1)}</td>
              <td></td>
              <td className="font-mono text-xs text-right font-bold">{totals.sr.toFixed(1)}</td>
              <td className="font-mono text-xs text-right font-bold">{$f(totals.specialTot)}</td>
              <td className="font-mono text-xs text-right font-bold">{totals.totalHrs.toFixed(1)}</td>
              <td className="font-mono text-xs text-right font-bold">{$f(totals.benefit)}</td>
              <td className="font-mono text-xs text-right font-bold">{$f(totals.fund)}</td>
              <td className="font-mono text-xs text-right font-bold">{$f(totals.deduction)}</td>
              <td className="font-mono text-xs text-right font-bold">{$f(totals.gross)}</td>
            </tr>
          )}
          {activeEmps.length === 0 && (
            <tr><td colSpan={15} className="text-center text-muted-foreground text-sm py-6">No hours entered for this day.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function DayTab({
  dayNum, event, employees, timeEntries, updateHour, saveDay, saving,
  dayViewMode, setDayViewMode, loadDailyStatement, dailyStatement,
  handleDayStatementPdf, empFilter, setEmpFilter, fp, bp, dp, isEditor,
}) {
  const isStatement = dayViewMode === 'statement';
  const dq = empFilter.toLowerCase();

  const dayFiltered = useMemo(() =>
    dq ? employees.filter(e => e.name.toLowerCase().includes(dq) || (e.dept_emp_num || '').toLowerCase().includes(dq)) : employees,
    [employees, dq]
  );

  const getVal = (empId, field) => timeEntries[empId]?.[field] || 0;

  const totals = useMemo(() => {
    const result = { hours: {}, totalHrs: 0, gross: 0 };
    HOUR_FIELDS.forEach(f => { result.hours[f] = employees.reduce((s, emp) => s + (timeEntries[emp.id]?.[f] || 0), 0); });
    result.totalHrs = employees.reduce((s, emp) => {
      const te = timeEntries[emp.id] || {};
      return s + (te.st_r1 || 0) + (te.ot_r1 || 0) + (te.dt_r1 || 0) + (te.st_r2 || 0) + (te.ot_r2 || 0) + (te.dt_r2 || 0);
    }, 0);
    result.gross = employees.reduce((s, emp) => {
      const te = timeEntries[emp.id] || {};
      return s + calcGross(emp.rate1 || 0, emp.rate2 || 0, emp.special_rate || 0, te.st_r1 || 0, te.ot_r1 || 0, te.dt_r1 || 0, te.st_r2 || 0, te.ot_r2 || 0, te.dt_r2 || 0, te.sr_hours || 0);
    }, 0);
    return result;
  }, [employees, timeEntries]);

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <div>
            <p className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">
              Day {dayNum} {event.days?.[dayNum]?.date ? `- ${event.days[dayNum].date}` : ''}
            </p>
            {event.notes?.[dayNum] && <p className="text-xs text-muted-foreground mt-1">{event.notes[dayNum]}</p>}
          </div>
          <div className="flex border border-border rounded-sm overflow-hidden ml-4">
            <button onClick={() => setDayViewMode('input')}
              className={`px-3 py-1 text-xs font-semibold uppercase tracking-wider transition-colors ${!isStatement ? 'bg-primary text-primary-foreground' : 'bg-background text-muted-foreground hover:bg-muted'}`}
              data-testid="day-mode-input">
              <Edit3 className="h-3 w-3 inline mr-1" />Input
            </button>
            <button onClick={() => { setDayViewMode('statement'); loadDailyStatement(dayNum); }}
              className={`px-3 py-1 text-xs font-semibold uppercase tracking-wider transition-colors ${isStatement ? 'bg-primary text-primary-foreground' : 'bg-background text-muted-foreground hover:bg-muted'}`}
              data-testid="day-mode-statement">
              <Eye className="h-3 w-3 inline mr-1" />Statement
            </button>
          </div>
          <div className="relative ml-2">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input value={empFilter} onChange={e => setEmpFilter(e.target.value)}
              placeholder="Filter employees..." className="rounded-sm pl-7 h-8 w-48 text-sm" data-testid="day-employee-search" />
            {empFilter && <button onClick={() => setEmpFilter('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"><X className="h-3 w-3" /></button>}
          </div>
          {dq && <span className="text-xs text-muted-foreground">{dayFiltered.length}/{employees.length}</span>}
        </div>
        {!isStatement && isEditor && (
          <Button onClick={saveDay} disabled={saving} className="rounded-sm gap-2" data-testid="save-day-button">
            <Save className="h-4 w-4" /> {saving ? 'Saving...' : 'Save Day'}
          </Button>
        )}
        {isStatement && (
          <Button variant="outline" onClick={() => handleDayStatementPdf(dayNum)} className="rounded-sm gap-2" data-testid="print-day-statement-pdf">
            <Printer className="h-4 w-4" /> Print PDF
          </Button>
        )}
      </div>

      {isStatement ? (
        <DailyStatement dailyStatement={dailyStatement} dayNum={dayNum} />
      ) : (
        <>
          <div className="overflow-x-auto border border-border">
            <table className="payroll-table w-full border-collapse">
              <thead>
                <tr>
                  <th className="text-left">#</th>
                  <th className="text-left">Employee</th>
                  <th className="text-left">Dept</th>
                  <th className="text-center" colSpan={3}>Rate 1 Hours</th>
                  <th className="text-center r2-col" colSpan={3}>Rate 2 Hours</th>
                  <th>SR</th>
                  <th>HRS</th>
                  <th>Gross</th>
                </tr>
                <tr>
                  <th></th><th></th><th></th>
                  <th>ST</th><th>OT</th><th>DT</th>
                  <th className="r2-col">ST</th><th className="r2-col">OT</th><th className="r2-col">DT</th>
                  <th>Hrs</th><th></th><th></th>
                </tr>
              </thead>
              <tbody>
                {dayFiltered.map((emp, i) => {
                  const s1 = getVal(emp.id, 'st_r1'), o1 = getVal(emp.id, 'ot_r1'), d1 = getVal(emp.id, 'dt_r1');
                  const s2 = getVal(emp.id, 'st_r2'), o2 = getVal(emp.id, 'ot_r2'), d2 = getVal(emp.id, 'dt_r2');
                  const sr = getVal(emp.id, 'sr_hours');
                  const hrs = s1 + o1 + d1 + s2 + o2 + d2;
                  const gross = calcGross(emp.rate1 || 0, emp.rate2 || 0, emp.special_rate || 0, s1, o1, d1, s2, o2, d2, sr);
                  return (
                    <tr key={emp.id} className={i % 2 === 0 ? '' : 'bg-muted/30'}>
                      <td className="font-mono text-xs text-muted-foreground">{i + 1}</td>
                      <td className="text-sm font-medium max-w-[140px] truncate">{emp.name}</td>
                      <td className="text-xs text-muted-foreground">{emp.dept_emp_num}</td>
                      {HOUR_FIELDS.map((f, fi) => (
                        <td key={f} className={`p-0 ${f.includes('r2') ? 'r2-col' : ''}`}>
                          <input type="number" step="0.5" min="0" value={getVal(emp.id, f) || ''}
                            onChange={e => updateHour(emp.id, f, e.target.value)}
                            data-testid={`entry-${emp.id}-${f}`}
                            tabIndex={i * 7 + fi + 1}
                            data-row={i} data-col={fi}
                            readOnly={!isEditor}
                            onKeyDown={e => {
                              if (e.key === 'Enter') {
                                e.preventDefault();
                                const nextRow = e.shiftKey ? i - 1 : i + 1;
                                const next = e.currentTarget.closest('tbody').querySelector(`[data-row="${nextRow}"][data-col="${fi}"]`);
                                if (next) next.focus();
                              }
                            }}
                            placeholder="0" />
                        </td>
                      ))}
                      <td className="calc-cell font-mono text-xs">{hrs.toFixed(1)}</td>
                      <td className="calc-cell font-mono text-xs font-semibold">{$f(gross)}</td>
                    </tr>
                  );
                })}
                {employees.length > 0 && (
                  <tr className="total-row">
                    <td></td><td className="font-semibold">TOTALS</td><td></td>
                    {HOUR_FIELDS.map(f => (
                      <td key={f} className={`font-mono text-xs text-right font-bold ${f.includes('r2') ? 'r2-col' : ''}`}>{totals.hours[f].toFixed(1)}</td>
                    ))}
                    <td className="font-mono text-xs text-right font-bold">{totals.totalHrs.toFixed(1)}</td>
                    <td className="font-mono text-xs text-right font-bold">{$f(totals.gross)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {employees.length === 0 && (
            <p className="text-sm text-muted-foreground mt-4">Add employees in the Employees tab first.</p>
          )}
        </>
      )}
    </div>
  );
}
