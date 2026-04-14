import { useMemo } from 'react';
import { Button } from '../ui/button';
import { $f, sumField } from '../../lib/payroll';
import { FileSpreadsheet, FileText } from 'lucide-react';

export default function SummaryTab({ summaryData, handleExport, handleFullReportPdf }) {
  const emps = useMemo(() => summaryData?.employees || [], [summaryData?.employees]);

  const totals = useMemo(() => ({
    r1_st: sumField(emps, 'r1_st'), r1_ot: sumField(emps, 'r1_ot'), r1_dt: sumField(emps, 'r1_dt'),
    r2_st: sumField(emps, 'r2_st'), r2_ot: sumField(emps, 'r2_ot'), r2_dt: sumField(emps, 'r2_dt'),
    sr_hours: sumField(emps, 'sr_hours'), special_tot: sumField(emps, 'special_tot'),
    total_hours: sumField(emps, 'total_hours'), benefit_co: sumField(emps, 'benefit_co'),
    fund_co: sumField(emps, 'fund_co'), deduction: sumField(emps, 'deduction'), gross: sumField(emps, 'gross'),
  }), [emps]);

  if (!summaryData) return <p className="p-4 text-muted-foreground text-sm">Loading summary...</p>;

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Sum-Totals</p>
        <div className="flex gap-2">
          <Button variant="outline" className="rounded-sm gap-2 text-sm" onClick={() => handleExport('excel')} data-testid="export-excel-button">
            <FileSpreadsheet className="h-4 w-4" /> Excel
          </Button>
          <Button variant="outline" className="rounded-sm gap-2 text-sm" onClick={() => handleExport('pdf')} data-testid="export-pdf-button">
            <FileText className="h-4 w-4" /> Summary PDF
          </Button>
          <Button className="rounded-sm gap-2 text-sm" onClick={handleFullReportPdf} data-testid="export-full-pdf-button">
            <FileText className="h-4 w-4" /> Full Report PDF
          </Button>
        </div>
      </div>
      <div className="overflow-x-auto border border-border">
        <table className="payroll-table w-full border-collapse">
          <thead>
            <tr>
              <th className="text-left">#</th>
              <th className="text-left">Employee</th>
              <th className="text-left">Dept</th>
              <th>Rate 1</th>
              <th>R1 ST</th><th>R1 OT</th><th>R1 DT</th>
              <th className="r2-col">Rate 2</th>
              <th className="r2-col">R2 ST</th><th className="r2-col">R2 OT</th><th className="r2-col">R2 DT</th>
              <th>SR$</th><th>SR Hrs</th><th>SR Tot</th>
              <th>Hrs</th><th>Benefit</th><th>Fund</th><th>Deduct</th><th>Gross</th>
            </tr>
          </thead>
          <tbody>
            {emps.map((emp, i) => (
              <tr key={emp.employee_id} className={i % 2 === 0 ? '' : 'bg-muted/30'}>
                <td className="font-mono text-xs text-muted-foreground">{i + 1}</td>
                <td className="text-sm font-medium">{emp.name}</td>
                <td className="text-xs text-muted-foreground">{emp.dept_emp_num}</td>
                <td className="font-mono text-xs text-right">{$f(emp.rate1)}</td>
                <td className="font-mono text-xs text-right">{emp.r1_st?.toFixed(1)}</td>
                <td className="font-mono text-xs text-right">{emp.r1_ot?.toFixed(1)}</td>
                <td className="font-mono text-xs text-right">{emp.r1_dt?.toFixed(1)}</td>
                <td className="font-mono text-xs text-right r2-col">{$f(emp.rate2)}</td>
                <td className="font-mono text-xs text-right r2-col">{emp.r2_st?.toFixed(1)}</td>
                <td className="font-mono text-xs text-right r2-col">{emp.r2_ot?.toFixed(1)}</td>
                <td className="font-mono text-xs text-right r2-col">{emp.r2_dt?.toFixed(1)}</td>
                <td className="font-mono text-xs text-right">{$f(emp.special_rate)}</td>
                <td className="font-mono text-xs text-right">{emp.sr_hours?.toFixed(1)}</td>
                <td className="font-mono text-xs text-right">{$f(emp.special_tot)}</td>
                <td className="font-mono text-xs text-right font-semibold">{emp.total_hours?.toFixed(1)}</td>
                <td className="font-mono text-xs text-right">{$f(emp.benefit_co)}</td>
                <td className="font-mono text-xs text-right">{$f(emp.fund_co)}</td>
                <td className="font-mono text-xs text-right">{$f(emp.deduction)}</td>
                <td className="font-mono text-xs text-right font-bold">{$f(emp.gross)}</td>
              </tr>
            ))}
            {emps.length > 0 && (
              <tr className="total-row">
                <td></td><td className="font-semibold">TOTALS</td><td></td>
                <td></td>
                {['r1_st', 'r1_ot', 'r1_dt'].map(k => (
                  <td key={k} className="font-mono text-xs text-right font-bold">{totals[k].toFixed(1)}</td>
                ))}
                <td></td>
                {['r2_st', 'r2_ot', 'r2_dt'].map(k => (
                  <td key={k} className="font-mono text-xs text-right font-bold r2-col">{totals[k].toFixed(1)}</td>
                ))}
                <td></td>
                <td className="font-mono text-xs text-right font-bold">{totals.sr_hours.toFixed(1)}</td>
                <td className="font-mono text-xs text-right font-bold">{$f(totals.special_tot)}</td>
                <td className="font-mono text-xs text-right font-bold">{totals.total_hours.toFixed(1)}</td>
                <td className="font-mono text-xs text-right font-bold">{$f(totals.benefit_co)}</td>
                <td className="font-mono text-xs text-right font-bold">{$f(totals.fund_co)}</td>
                <td className="font-mono text-xs text-right font-bold">{$f(totals.deduction)}</td>
                <td className="font-mono text-xs text-right font-bold">{$f(totals.gross)}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
