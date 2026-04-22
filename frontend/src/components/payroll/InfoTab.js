import { useState, useMemo } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Calendar } from '../ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover';
import { Save, CalendarDays } from 'lucide-react';
import { DAYS } from '../../lib/payroll';

function DatePicker({ value, onChange, testId, placeholder }) {
  const [open, setOpen] = useState(false);
  const selected = value ? new Date(value + 'T00:00:00') : undefined;

  const formatDate = (d) => {
    if (!d) return '';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const handleSelect = (date) => {
    if (date) {
      const y = date.getFullYear();
      const m = String(date.getMonth() + 1).padStart(2, '0');
      const d = String(date.getDate()).padStart(2, '0');
      onChange(`${y}-${m}-${d}`);
    } else {
      onChange('');
    }
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" className="w-full justify-start text-left font-normal rounded-sm mt-1 h-9 text-sm"
          data-testid={testId}>
          <CalendarDays className="mr-2 h-4 w-4 text-muted-foreground" />
          {selected ? formatDate(selected) : <span className="text-muted-foreground">{placeholder}</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar mode="single" selected={selected} onSelect={handleSelect} initialFocus />
      </PopoverContent>
    </Popover>
  );
}

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

  const payPeriodDays = useMemo(() => {
    const start = event.pay_period_start;
    const end = event.pay_period_end;
    if (!start || !end) return null;
    const s = new Date(start + 'T00:00:00');
    const e = new Date(end + 'T00:00:00');
    const diff = Math.round((e - s) / (1000 * 60 * 60 * 24)) + 1;
    return diff > 0 ? diff : null;
  }, [event.pay_period_start, event.pay_period_end]);

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
        <p className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-3">Pay Period</p>
        <div className="grid grid-cols-3 gap-4 items-end">
          <div>
            <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Start Date</Label>
            <DatePicker
              value={event.pay_period_start || ''}
              onChange={v => updateEventField(p => ({ ...p, pay_period_start: v }))}
              testId="info-pay_period_start"
              placeholder="Select start date"
            />
          </div>
          <div>
            <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">End Date</Label>
            <DatePicker
              value={event.pay_period_end || ''}
              onChange={v => updateEventField(p => ({ ...p, pay_period_end: v }))}
              testId="info-pay_period_end"
              placeholder="Select end date"
            />
          </div>
          <div>
            {payPeriodDays && (
              <p className="text-sm text-muted-foreground pb-2" data-testid="pay-period-days">
                {payPeriodDays} day{payPeriodDays !== 1 ? 's' : ''}
              </p>
            )}
          </div>
        </div>
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
