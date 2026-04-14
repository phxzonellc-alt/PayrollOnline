import { useMemo } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Save } from 'lucide-react';
import { DAYS } from '../../lib/payroll';

export default function InfoTab({ event, updateEventField, saveEvent, saving, isEditor }) {
  const fp = event.fund_pct || 0.02;
  const bp = event.benefit_pct || 0.21;
  const dp = event.deduction_pct || 0.05;

  const infoFields = useMemo(() => [
    ['event_name', 'Event Name'], ['job_number', 'Job Number'], ['employer', 'Employer'],
    ['venue', 'Venue'], ['payroll_name', 'Payroll Name'], ['contact_email', 'Email'], ['cell_phone', 'Cell Phone']
  ], []);

  const pctFields = useMemo(() => [
    ['fund_pct', 'Fund %', fp], ['benefit_pct', 'Benefit %', bp], ['deduction_pct', 'Deduction %', dp]
  ], [fp, bp, dp]);

  return (
    <div className="max-w-3xl space-y-4 p-4">
      <div className="grid grid-cols-2 gap-4">
        {infoFields.map(([k, l]) => (
          <div key={k}>
            <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">{l}</Label>
            <Input value={event[k] || ''} onChange={e => updateEventField(p => ({ ...p, [k]: e.target.value }))}
              className="mt-1 rounded-sm" data-testid={`info-${k}`} />
          </div>
        ))}
      </div>
      <div className="border-t border-border pt-4">
        <p className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-3">Company Branding (PDF Header)</p>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Company Name</Label>
            <Input value={event.company_name || ''} onChange={e => updateEventField(p => ({ ...p, company_name: e.target.value }))}
              placeholder="Your Company LLC" className="mt-1 rounded-sm" data-testid="info-company_name" />
          </div>
          <div>
            <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Company Email</Label>
            <Input type="email" value={event.company_email || ''} onChange={e => updateEventField(p => ({ ...p, company_email: e.target.value }))}
              placeholder="payroll@company.com" className="mt-1 rounded-sm" data-testid="info-company_email" />
          </div>
          <div>
            <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Company Phone</Label>
            <Input value={event.company_phone || ''} onChange={e => updateEventField(p => ({ ...p, company_phone: e.target.value }))}
              placeholder="(555) 123-4567" className="mt-1 rounded-sm" data-testid="info-company_phone" />
          </div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-4 border-t border-border pt-4">
        {pctFields.map(([k, l, v]) => (
          <div key={k}>
            <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">{l}</Label>
            <Input type="number" step="0.01" value={event[k] ?? v}
              onChange={e => updateEventField(p => ({ ...p, [k]: parseFloat(e.target.value) || 0 }))}
              className="mt-1 rounded-sm font-mono" data-testid={`info-${k}`} />
          </div>
        ))}
      </div>
      <div className="border-t border-border pt-4">
        <p className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-3">Day Dates & Notes</p>
        <div className="grid grid-cols-2 gap-3">
          {DAYS.map(d => (
            <div key={d} className="flex gap-2 items-center">
              <span className="text-xs font-semibold text-muted-foreground w-10">D{d}</span>
              <Input type="date" value={event.days?.[d]?.date || ''}
                onChange={e => updateEventField(p => ({ ...p, days: { ...(p.days || {}), [d]: { ...(p.days?.[d] || {}), date: e.target.value } } }))}
                className="rounded-sm text-sm flex-1" data-testid={`day-${d}-date`} />
              <Input value={event.notes?.[d] || ''} placeholder="Note..."
                onChange={e => updateEventField(p => ({ ...p, notes: { ...(p.notes || {}), [d]: e.target.value } }))}
                className="rounded-sm text-sm flex-1" data-testid={`day-${d}-note`} />
            </div>
          ))}
        </div>
      </div>
      {isEditor && <Button onClick={saveEvent} disabled={saving} className="rounded-sm gap-2" data-testid="save-info-button">
        <Save className="h-4 w-4" /> {saving ? 'Saving...' : 'Save Information'}
      </Button>}
    </div>
  );
}
