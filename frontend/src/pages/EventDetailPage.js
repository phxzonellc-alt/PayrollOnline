import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import '@/App.css';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { toast } from 'sonner';
import { ArrowLeft, Save, Download, Plus, Trash2, FileSpreadsheet, FileText, Upload, Pencil, Check, X, Eye, Edit3, Printer, GripVertical, ArrowUpDown, ArrowUp, ArrowDown, Search } from 'lucide-react';

const DAYS = [1,2,3,4,5,6,7,8,9,10];

function calcGross(r1, r2, sr, s1, o1, d1, s2, o2, d2, srh) {
  if ((s1+o1+d1) === 0) return (r2*s2) + (r2*1.5*o2) + (r2*2*d2) + (sr*srh);
  return (r1*s1) + (r1*1.5*o1) + (r1*2*d1) + (sr*srh);
}

const $f = (v) => '$' + (v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function EventDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { logout, user: currentUser } = useAuth();
  const isAdmin = currentUser?.role === 'admin';
  const isEditor = currentUser?.role === 'admin' || currentUser?.role === 'user';
  const [event, setEvent] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [timeEntries, setTimeEntries] = useState({});
  const [summaryData, setSummaryData] = useState(null);
  const [activeTab, setActiveTab] = useState('info');
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [newEmp, setNewEmp] = useState({ name: '', dept_emp_num: '', rate1: '', rate2: '', special_rate: '' });
  const [editingEmp, setEditingEmp] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [dayViewMode, setDayViewMode] = useState('input');
  const [dailyStatement, setDailyStatement] = useState(null);
  const [dragIdx, setDragIdx] = useState(null);
  const [sortField, setSortField] = useState(null);
  const [sortDir, setSortDir] = useState('asc');
  const [empFilter, setEmpFilter] = useState('');
  const prevTabRef = useRef('info');
  const infoDirtyRef = useRef(false);
  const dayDirtyRef = useRef(false);
  const timeEntriesRef = useRef({});
  const employeesRef = useRef([]);
  const eventRef = useRef(null);

  const loadEvent = useCallback(async () => {
    try {
      const res = await api.get(`/events/${id}`);
      setEvent(res.data);
    } catch { toast.error('Failed to load event'); navigate('/'); }
  }, [id, navigate]);

  const loadEmployees = useCallback(async () => {
    try {
      const res = await api.get(`/events/${id}/employees`);
      setEmployees(res.data);
    } catch { toast.error('Failed to load employees'); }
  }, [id]);

  const loadTimeEntries = useCallback(async (day) => {
    try {
      const res = await api.get(`/events/${id}/time-entries?day=${day}`);
      const map = {};
      res.data.forEach(e => { map[e.employee_id] = e; });
      setTimeEntries(map);
    } catch { toast.error('Failed to load time entries'); }
  }, [id]);

  const loadSummary = useCallback(async () => {
    try {
      const res = await api.get(`/events/${id}/sum-totals`);
      setSummaryData(res.data);
    } catch { toast.error('Failed to load summary'); }
  }, [id]);

  const loadDailyStatement = useCallback(async (day) => {
    try {
      const res = await api.get(`/events/${id}/daily-statement/${day}`);
      setDailyStatement(res.data);
    } catch { toast.error('Failed to load daily statement'); }
  }, [id]);

  useEffect(() => {
    Promise.all([loadEvent(), loadEmployees()]).finally(() => setLoading(false));
  }, [loadEvent, loadEmployees]);

  // Keep refs in sync
  useEffect(() => { timeEntriesRef.current = timeEntries; }, [timeEntries]);
  useEffect(() => { employeesRef.current = employees; }, [employees]);
  useEffect(() => { eventRef.current = event; }, [event]);

  // Silent save helpers (no toast, no loading state)
  const silentSaveDay = useCallback(async (tab) => {
    if (!dayDirtyRef.current) return;
    const dayNum = parseInt(tab.split('-')[1]);
    const emps = employeesRef.current;
    const te = timeEntriesRef.current;
    if (!emps.length) return;
    const entries = emps.map(emp => ({
      employee_id: emp.id, day_number: dayNum,
      st_r1: te[emp.id]?.st_r1 || 0, ot_r1: te[emp.id]?.ot_r1 || 0,
      dt_r1: te[emp.id]?.dt_r1 || 0, st_r2: te[emp.id]?.st_r2 || 0,
      ot_r2: te[emp.id]?.ot_r2 || 0, dt_r2: te[emp.id]?.dt_r2 || 0,
      sr_hours: te[emp.id]?.sr_hours || 0,
    }));
    try { await api.post(`/events/${id}/time-entries/batch`, { entries }); } catch {}
    dayDirtyRef.current = false;
  }, [id]);

  const silentSaveInfo = useCallback(async () => {
    if (!infoDirtyRef.current || !eventRef.current) return;
    try { await api.put(`/events/${id}`, eventRef.current); } catch {}
    infoDirtyRef.current = false;
  }, [id]);

  // Auto-save when switching tabs
  const handleTabChange = useCallback(async (newTab) => {
    const prev = prevTabRef.current;
    if (prev === newTab) return;
    // Save previous tab
    if (prev === 'info') await silentSaveInfo();
    else if (prev.startsWith('day-')) await silentSaveDay(prev);
    prevTabRef.current = newTab;
    setActiveTab(newTab);
  }, [silentSaveInfo, silentSaveDay]);

  // Auto-save on page unmount
  useEffect(() => {
    return () => {
      const tab = prevTabRef.current;
      if (tab === 'info' && infoDirtyRef.current && eventRef.current) {
        api.put(`/events/${id}`, eventRef.current).catch(() => {});
      } else if (tab.startsWith('day-') && dayDirtyRef.current) {
        const dayNum = parseInt(tab.split('-')[1]);
        const entries = employeesRef.current.map(emp => ({
          employee_id: emp.id, day_number: dayNum,
          st_r1: timeEntriesRef.current[emp.id]?.st_r1 || 0, ot_r1: timeEntriesRef.current[emp.id]?.ot_r1 || 0,
          dt_r1: timeEntriesRef.current[emp.id]?.dt_r1 || 0, st_r2: timeEntriesRef.current[emp.id]?.st_r2 || 0,
          ot_r2: timeEntriesRef.current[emp.id]?.ot_r2 || 0, dt_r2: timeEntriesRef.current[emp.id]?.dt_r2 || 0,
          sr_hours: timeEntriesRef.current[emp.id]?.sr_hours || 0,
        }));
        api.post(`/events/${id}/time-entries/batch`, { entries }).catch(() => {});
      }
    };
  }, [id]);

  useEffect(() => {
    if (activeTab.startsWith('day-')) {
      const dayNum = parseInt(activeTab.split('-')[1]);
      loadTimeEntries(dayNum);
      if (dayViewMode === 'statement') {
        loadDailyStatement(dayNum);
      }
    } else if (activeTab === 'summary') {
      loadSummary();
    }
  }, [activeTab, loadTimeEntries, loadSummary, loadDailyStatement, dayViewMode]);

  const saveEvent = async () => {
    setSaving(true);
    try {
      const res = await api.put(`/events/${id}`, event);
      setEvent(res.data);
      infoDirtyRef.current = false;
      toast.success('Event saved');
    } catch { toast.error('Failed to save'); }
    finally { setSaving(false); }
  };

  const addEmployee = async (e) => {
    e.preventDefault();
    try {
      const res = await api.post(`/events/${id}/employees`, {
        ...newEmp, rate1: parseFloat(newEmp.rate1) || 0,
        rate2: parseFloat(newEmp.rate2) || 0, special_rate: parseFloat(newEmp.special_rate) || 0
      });
      setEmployees(prev => [...prev, res.data]);
      setNewEmp({ name: '', dept_emp_num: '', rate1: '', rate2: '', special_rate: '' });
      toast.success('Employee added');
    } catch { toast.error('Failed to add employee'); }
  };

  const deleteEmployee = async (empId) => {
    if (!window.confirm('Delete this employee?')) return;
    try {
      await api.delete(`/events/${id}/employees/${empId}`);
      setEmployees(prev => prev.filter(e => e.id !== empId));
      toast.success('Employee deleted');
    } catch { toast.error('Failed to delete'); }
  };

  const startEdit = (emp) => {
    setEditingEmp(emp.id);
    setEditForm({ name: emp.name, dept_emp_num: emp.dept_emp_num, rate1: emp.rate1, rate2: emp.rate2, special_rate: emp.special_rate });
  };

  const cancelEdit = () => { setEditingEmp(null); setEditForm({}); };

  const saveEdit = async (empId) => {
    try {
      const res = await api.put(`/events/${id}/employees/${empId}`, {
        name: editForm.name, dept_emp_num: editForm.dept_emp_num,
        rate1: parseFloat(editForm.rate1) || 0, rate2: parseFloat(editForm.rate2) || 0,
        special_rate: parseFloat(editForm.special_rate) || 0,
      });
      setEmployees(prev => prev.map(e => e.id === empId ? res.data : e));
      setEditingEmp(null);
      toast.success('Employee updated');
    } catch { toast.error('Failed to update'); }
  };

  const handleImportFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await api.post(`/events/${id}/employees/import`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setEmployees(prev => [...prev, ...res.data.employees]);
      toast.success(`Imported ${res.data.imported} employees`);
    } catch { toast.error('Import failed. Check file format (CSV/Excel with headers: Name, Dept, Rate 1, Rate 2, Special Rate)'); }
    e.target.value = '';
  };

  const handleDragStart = (idx) => { setDragIdx(idx); };
  const handleDragOver = (e) => { e.preventDefault(); };
  const handleDrop = async (dropIdx) => {
    if (dragIdx === null || dragIdx === dropIdx) { setDragIdx(null); return; }
    const updated = [...employees];
    const [moved] = updated.splice(dragIdx, 1);
    updated.splice(dropIdx, 0, moved);
    setEmployees(updated);
    setDragIdx(null);
    try {
      const res = await api.post(`/events/${id}/employees/reorder`, { order: updated.map(e => e.id) });
      setEmployees(res.data);
      toast.success('Order saved');
    } catch { toast.error('Failed to save order'); }
  };

  const handleSort = async (field) => {
    let newDir, newField;
    if (sortField === field) {
      if (sortDir === 'asc') { newDir = 'desc'; newField = field; }
      else { newDir = 'asc'; newField = null; } // third click → reset
    } else {
      newDir = 'asc'; newField = field;
    }
    setSortField(newField);
    setSortDir(newDir);
    if (!newField) {
      await loadEmployees(); // reload original order
      return;
    }
    const sorted = [...employees].sort((a, b) => {
      const va = (a[field] || '').toString().toLowerCase();
      const vb = (b[field] || '').toString().toLowerCase();
      return newDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
    });
    setEmployees(sorted);
    try {
      const res = await api.post(`/events/${id}/employees/reorder`, { order: sorted.map(e => e.id) });
      setEmployees(res.data);
      toast.success(`Sorted by ${field === 'name' ? 'Name' : 'Dept'} ${newDir === 'asc' ? 'A-Z' : 'Z-A'}`);
    } catch { toast.error('Failed to save order'); }
  };

  const SortIcon = ({ field }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3 w-3 inline ml-1 opacity-40" />;
    return sortDir === 'asc'
      ? <ArrowUp className="h-3 w-3 inline ml-1 text-primary" />
      : <ArrowDown className="h-3 w-3 inline ml-1 text-primary" />;
  };

  const updateEventField = (updater) => {
    infoDirtyRef.current = true;
    setEvent(updater);
  };

  const updateHour = (empId, field, value) => {
    dayDirtyRef.current = true;
    setTimeEntries(prev => ({
      ...prev,
      [empId]: { ...(prev[empId] || {}), employee_id: empId, [field]: parseFloat(value) || 0 }
    }));
  };

  const saveDay = async () => {
    const dayNum = parseInt(activeTab.split('-')[1]);
    setSaving(true);
    try {
      const entries = employees.map(emp => ({
        employee_id: emp.id, day_number: dayNum,
        st_r1: timeEntries[emp.id]?.st_r1 || 0, ot_r1: timeEntries[emp.id]?.ot_r1 || 0,
        dt_r1: timeEntries[emp.id]?.dt_r1 || 0, st_r2: timeEntries[emp.id]?.st_r2 || 0,
        ot_r2: timeEntries[emp.id]?.ot_r2 || 0, dt_r2: timeEntries[emp.id]?.dt_r2 || 0,
        sr_hours: timeEntries[emp.id]?.sr_hours || 0,
      }));
      await api.post(`/events/${id}/time-entries/batch`, { entries });
      toast.success(`Day ${dayNum} saved`);
    } catch { toast.error('Failed to save'); }
    finally { setSaving(false); }
  };

  const handleExport = async (type) => {
    try {
      const url = `${process.env.REACT_APP_BACKEND_URL}/api/events/${id}/export/${type}`;
      const res = await fetch(url, { credentials: 'include' });
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `payroll_${event?.event_name || id}.${type === 'excel' ? 'xlsx' : 'pdf'}`;
      link.click();
      URL.revokeObjectURL(link.href);
      toast.success(`${type.toUpperCase()} exported`);
    } catch { toast.error('Export failed'); }
  };

  const handleDownloadTemplate = async () => {
    try {
      const url = `${process.env.REACT_APP_BACKEND_URL}/api/employees/template`;
      const res = await fetch(url, { credentials: 'include' });
      if (!res.ok) throw new Error('Template download failed');
      const blob = await res.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'employee_import_template.csv';
      link.click();
      URL.revokeObjectURL(link.href);
      toast.success('Template downloaded');
    } catch { toast.error('Template download failed'); }
  };

  const handleDayStatementPdf = async (dayNum) => {
    try {
      const url = `${process.env.REACT_APP_BACKEND_URL}/api/events/${id}/daily-statement/${dayNum}/pdf`;
      const res = await fetch(url, { credentials: 'include' });
      if (!res.ok) throw new Error('PDF export failed');
      const blob = await res.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `${event?.event_name || 'payroll'}_day${dayNum}_statement.pdf`;
      link.click();
      URL.revokeObjectURL(link.href);
      toast.success(`Day ${dayNum} statement PDF exported`);
    } catch { toast.error('PDF export failed'); }
  };

  const handleFullReportPdf = async () => {
    try {
      toast.info('Generating full report...');
      const url = `${process.env.REACT_APP_BACKEND_URL}/api/events/${id}/export/full-pdf`;
      const res = await fetch(url, { credentials: 'include' });
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `${event?.event_name || 'payroll'}_full_report.pdf`;
      link.click();
      URL.revokeObjectURL(link.href);
      toast.success('Full report PDF exported');
    } catch { toast.error('Full report export failed'); }
  };

  if (loading || !event) return <div className="min-h-screen bg-background flex items-center justify-center"><p className="text-muted-foreground">Loading...</p></div>;

  const fp = event.fund_pct || 0.02;
  const bp = event.benefit_pct || 0.21;
  const dp = event.deduction_pct || 0.05;

  const renderInfoTab = () => (
    <div className="max-w-3xl space-y-4 p-4">
      <div className="grid grid-cols-2 gap-4">
        {[['event_name','Event Name'],['job_number','Job Number'],['employer','Employer'],['venue','Venue'],
          ['payroll_name','Payroll Name'],['contact_email','Email'],['cell_phone','Cell Phone']].map(([k,l]) => (
          <div key={k}>
            <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">{l}</Label>
            <Input value={event[k] || ''} onChange={e => updateEventField(p => ({...p, [k]: e.target.value}))}
              className="mt-1 rounded-sm" data-testid={`info-${k}`} />
          </div>
        ))}
      </div>
      <div className="border-t border-border pt-4">
        <p className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-3">Company Branding (PDF Header)</p>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Company Name</Label>
            <Input value={event.company_name || ''} onChange={e => updateEventField(p => ({...p, company_name: e.target.value}))}
              placeholder="Your Company LLC" className="mt-1 rounded-sm" data-testid="info-company_name" />
          </div>
          <div>
            <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Company Email</Label>
            <Input type="email" value={event.company_email || ''} onChange={e => updateEventField(p => ({...p, company_email: e.target.value}))}
              placeholder="payroll@company.com" className="mt-1 rounded-sm" data-testid="info-company_email" />
          </div>
          <div>
            <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Company Phone</Label>
            <Input value={event.company_phone || ''} onChange={e => updateEventField(p => ({...p, company_phone: e.target.value}))}
              placeholder="(555) 123-4567" className="mt-1 rounded-sm" data-testid="info-company_phone" />
          </div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-4 border-t border-border pt-4">
        {[['fund_pct','Fund %',fp],['benefit_pct','Benefit %',bp],['deduction_pct','Deduction %',dp]].map(([k,l,v]) => (
          <div key={k}>
            <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">{l}</Label>
            <Input type="number" step="0.01" value={event[k] ?? v}
              onChange={e => updateEventField(p => ({...p, [k]: parseFloat(e.target.value) || 0}))}
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
                onChange={e => updateEventField(p => ({...p, days: {...(p.days||{}), [d]: {...(p.days?.[d]||{}), date: e.target.value}}}))}
                className="rounded-sm text-sm flex-1" data-testid={`day-${d}-date`} />
              <Input value={event.notes?.[d] || ''} placeholder="Note..."
                onChange={e => updateEventField(p => ({...p, notes: {...(p.notes||{}), [d]: e.target.value}}))}
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

  const renderEmployeesTab = () => {
    const q = empFilter.toLowerCase();
    const filtered = q ? employees.filter(e => e.name.toLowerCase().includes(q) || (e.dept_emp_num || '').toLowerCase().includes(q)) : employees;
    return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <p className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">
            {employees.length} Employee{employees.length !== 1 ? 's' : ''}
          </p>
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input value={empFilter} onChange={e => setEmpFilter(e.target.value)}
              placeholder="Filter by name or dept..."
              className="rounded-sm pl-7 h-8 w-56 text-sm" data-testid="employee-search" />
            {empFilter && <button onClick={() => setEmpFilter('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"><X className="h-3 w-3" /></button>}
          </div>
          {q && <span className="text-xs text-muted-foreground">{filtered.length} match{filtered.length !== 1 ? 'es' : ''}</span>}
        </div>
        {isEditor && (
        <div className="flex gap-2">
          <Button variant="outline" className="rounded-sm gap-2 text-sm" onClick={handleDownloadTemplate} data-testid="download-template-button">
            <Download className="h-4 w-4" /> Template
          </Button>
          <label className="cursor-pointer">
            <input type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={handleImportFile} data-testid="import-file-input" />
            <Button variant="outline" className="rounded-sm gap-2 text-sm pointer-events-none" asChild>
              <span><Upload className="h-4 w-4" /> Import CSV/Excel</span>
            </Button>
          </label>
        </div>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="payroll-table w-full border-collapse">
          <thead>
            <tr>
              <th className="w-6"></th>
              <th className="text-left w-10">#</th>
              <th className="text-left cursor-pointer select-none hover:text-primary transition-colors" onClick={() => handleSort('name')} data-testid="sort-by-name">
                Name<SortIcon field="name" />
              </th>
              <th className="text-left cursor-pointer select-none hover:text-primary transition-colors" onClick={() => handleSort('dept_emp_num')} data-testid="sort-by-dept">
                Dept/Emp #<SortIcon field="dept_emp_num" />
              </th>
              <th className="text-right">Rate 1</th>
              <th className="text-right">Rate 2</th>
              <th className="text-right">Special Rate</th>
              {isEditor && <th className="w-20 text-center">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {filtered.map((emp, i) => (
              editingEmp === emp.id ? (
                <tr key={emp.id} className="bg-primary/5">
                  <td></td>
                  <td className="font-mono text-xs text-muted-foreground">{i+1}</td>
                  <td className="p-0"><input type="text" value={editForm.name}
                    onChange={e => setEditForm(p => ({...p, name: e.target.value}))}
                    className="w-full px-2 py-1 text-sm border border-ring bg-background focus:outline-none" data-testid={`edit-name-${emp.id}`} /></td>
                  <td className="p-0"><input type="text" value={editForm.dept_emp_num}
                    onChange={e => setEditForm(p => ({...p, dept_emp_num: e.target.value}))}
                    className="w-full px-2 py-1 text-sm border border-ring bg-background focus:outline-none" data-testid={`edit-dept-${emp.id}`} /></td>
                  <td className="p-0"><input type="number" step="0.01" value={editForm.rate1}
                    onChange={e => setEditForm(p => ({...p, rate1: e.target.value}))}
                    className="w-full px-2 py-1 text-sm font-mono text-right border border-ring bg-background focus:outline-none" data-testid={`edit-rate1-${emp.id}`} /></td>
                  <td className="p-0"><input type="number" step="0.01" value={editForm.rate2}
                    onChange={e => setEditForm(p => ({...p, rate2: e.target.value}))}
                    className="w-full px-2 py-1 text-sm font-mono text-right border border-ring bg-background focus:outline-none" data-testid={`edit-rate2-${emp.id}`} /></td>
                  <td className="p-0"><input type="number" step="0.01" value={editForm.special_rate}
                    onChange={e => setEditForm(p => ({...p, special_rate: e.target.value}))}
                    className="w-full px-2 py-1 text-sm font-mono text-right border border-ring bg-background focus:outline-none" data-testid={`edit-sr-${emp.id}`} /></td>
                  <td className="text-center">
                    <div className="flex gap-1 justify-center">
                      <Button variant="ghost" size="icon" className="h-6 w-6 rounded-sm text-green-600 hover:text-green-700 hover:bg-green-50"
                        onClick={() => saveEdit(emp.id)} data-testid={`save-edit-${emp.id}`}>
                        <Check className="h-3 w-3" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-6 w-6 rounded-sm text-muted-foreground hover:text-foreground"
                        onClick={cancelEdit} data-testid={`cancel-edit-${emp.id}`}>
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={emp.id}
                  draggable={isEditor}
                  onDragStart={() => isEditor && handleDragStart(i)}
                  onDragOver={isEditor ? handleDragOver : undefined}
                  onDrop={() => isEditor && handleDrop(i)}
                  className={`${i % 2 === 0 ? '' : 'bg-muted/30'} ${dragIdx === i ? 'opacity-40' : ''} transition-opacity`}>
                  {isEditor ? (
                  <td className="cursor-grab active:cursor-grabbing px-1" data-testid={`drag-handle-${emp.id}`}>
                    <GripVertical className="h-3.5 w-3.5 text-muted-foreground" />
                  </td>
                  ) : <td></td>}
                  <td className="font-mono text-xs text-muted-foreground">{i+1}</td>
                  <td>{emp.name}</td>
                  <td>{emp.dept_emp_num}</td>
                  <td className="text-right font-mono">{$f(emp.rate1)}</td>
                  <td className="text-right font-mono">{$f(emp.rate2)}</td>
                  <td className="text-right font-mono">{$f(emp.special_rate)}</td>
                  {isEditor && (
                  <td className="text-center">
                    <div className="flex gap-1 justify-center">
                      <Button variant="ghost" size="icon" className="h-6 w-6 rounded-sm text-muted-foreground hover:text-primary"
                        onClick={() => startEdit(emp)} data-testid={`edit-emp-${emp.id}`}>
                        <Pencil className="h-3 w-3" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-6 w-6 rounded-sm text-muted-foreground hover:text-destructive"
                        onClick={() => deleteEmployee(emp.id)} data-testid={`delete-emp-${emp.id}`}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </td>
                  )}
                </tr>
              )
            ))}
          </tbody>
        </table>
      </div>
      {isEditor && (
      <>
      <form onSubmit={addEmployee} className="mt-4 flex gap-2 items-end border-t border-border pt-4">
        <div className="flex-1">
          <Label className="text-xs text-muted-foreground">Name</Label>
          <Input value={newEmp.name} onChange={e => setNewEmp(p => ({...p, name: e.target.value}))}
            placeholder="Employee name" required className="rounded-sm" data-testid="new-emp-name" />
        </div>
        <div className="w-28">
          <Label className="text-xs text-muted-foreground">Dept/Emp#</Label>
          <Input value={newEmp.dept_emp_num} onChange={e => setNewEmp(p => ({...p, dept_emp_num: e.target.value}))}
            placeholder="Dept#" className="rounded-sm" data-testid="new-emp-dept" />
        </div>
        <div className="w-24">
          <Label className="text-xs text-muted-foreground">Rate 1</Label>
          <Input type="number" step="0.01" value={newEmp.rate1} onChange={e => setNewEmp(p => ({...p, rate1: e.target.value}))}
            placeholder="0.00" className="rounded-sm font-mono" data-testid="new-emp-rate1" />
        </div>
        <div className="w-24">
          <Label className="text-xs text-muted-foreground">Rate 2</Label>
          <Input type="number" step="0.01" value={newEmp.rate2} onChange={e => setNewEmp(p => ({...p, rate2: e.target.value}))}
            placeholder="0.00" className="rounded-sm font-mono" data-testid="new-emp-rate2" />
        </div>
        <div className="w-24">
          <Label className="text-xs text-muted-foreground">SR</Label>
          <Input type="number" step="0.01" value={newEmp.special_rate} onChange={e => setNewEmp(p => ({...p, special_rate: e.target.value}))}
            placeholder="0.00" className="rounded-sm font-mono" data-testid="new-emp-sr" />
        </div>
        <Button type="submit" className="rounded-sm gap-1" data-testid="add-employee-button">
          <Plus className="h-4 w-4" /> Add
        </Button>
      </form>
      <p className="text-xs text-muted-foreground mt-3">
        Import format: CSV or Excel with columns - Name, Dept/Emp Number, Rate 1, Rate 2, Special Rate
      </p>
      </>
      )}
    </div>
  ); };

  const renderDailyStatement = (dayNum) => {
    if (!dailyStatement || dailyStatement.day !== dayNum) return <p className="text-muted-foreground text-sm p-4">Loading statement...</p>;
    const emps = dailyStatement.employees || [];
    const stFp = dailyStatement.fund_pct, stBp = dailyStatement.benefit_pct, stDp = dailyStatement.deduction_pct;
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
              <th className="text-right">Benefit ({(stBp*100).toFixed(0)}%)</th>
              <th className="text-right">Fund ({(stFp*100).toFixed(0)}%)</th>
              <th className="text-right">Deduct ({(stDp*100).toFixed(0)}%)</th>
              <th className="text-right">Gross Salary</th>
            </tr>
          </thead>
          <tbody>
            {emps.map((emp, i) => {
              const hasData = emp.total_hours > 0 || emp.sr_hours > 0;
              if (!hasData) return null;
              const r2c = emp.used_r2 ? ' r2-col' : '';
              return (
                <tr key={emp.employee_id} className={i%2===0?'':'bg-muted/30'}>
                  <td className="font-mono text-xs text-muted-foreground">{i+1}</td>
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
            {emps.filter(e => e.total_hours > 0 || e.sr_hours > 0).length > 0 && (
              <tr className="total-row">
                <td></td><td className="font-semibold">TOTALS</td><td></td><td></td>
                <td className="font-mono text-xs text-right font-bold">{emps.reduce((s,e)=>s+e.st_hrs,0).toFixed(1)}</td>
                <td className="font-mono text-xs text-right font-bold">{emps.reduce((s,e)=>s+e.ot_hrs,0).toFixed(1)}</td>
                <td className="font-mono text-xs text-right font-bold">{emps.reduce((s,e)=>s+e.dt_hrs,0).toFixed(1)}</td>
                <td></td>
                <td className="font-mono text-xs text-right font-bold">{emps.reduce((s,e)=>s+e.sr_hours,0).toFixed(1)}</td>
                <td className="font-mono text-xs text-right font-bold">{$f(emps.reduce((s,e)=>s+e.special_tot,0))}</td>
                <td className="font-mono text-xs text-right font-bold">{emps.reduce((s,e)=>s+e.total_hours,0).toFixed(1)}</td>
                <td className="font-mono text-xs text-right font-bold">{$f(emps.reduce((s,e)=>s+e.benefit_co,0))}</td>
                <td className="font-mono text-xs text-right font-bold">{$f(emps.reduce((s,e)=>s+e.fund_co,0))}</td>
                <td className="font-mono text-xs text-right font-bold">{$f(emps.reduce((s,e)=>s+e.deduction,0))}</td>
                <td className="font-mono text-xs text-right font-bold">{$f(emps.reduce((s,e)=>s+e.gross,0))}</td>
              </tr>
            )}
            {emps.filter(e => e.total_hours > 0 || e.sr_hours > 0).length === 0 && (
              <tr><td colSpan={15} className="text-center text-muted-foreground text-sm py-6">No hours entered for this day.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    );
  };

  const renderDayTab = (dayNum) => {
    const getVal = (empId, field) => timeEntries[empId]?.[field] || 0;
    const hourFields = ['st_r1','ot_r1','dt_r1','st_r2','ot_r2','dt_r2','sr_hours'];
    const isStatement = dayViewMode === 'statement';
    const dq = empFilter.toLowerCase();
    const dayFiltered = dq ? employees.filter(e => e.name.toLowerCase().includes(dq) || (e.dept_emp_num || '').toLowerCase().includes(dq)) : employees;
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
              <button
                onClick={() => { setDayViewMode('input'); }}
                className={`px-3 py-1 text-xs font-semibold uppercase tracking-wider transition-colors ${!isStatement ? 'bg-primary text-primary-foreground' : 'bg-background text-muted-foreground hover:bg-muted'}`}
                data-testid="day-mode-input"
              >
                <Edit3 className="h-3 w-3 inline mr-1" />Input
              </button>
              <button
                onClick={() => { setDayViewMode('statement'); loadDailyStatement(dayNum); }}
                className={`px-3 py-1 text-xs font-semibold uppercase tracking-wider transition-colors ${isStatement ? 'bg-primary text-primary-foreground' : 'bg-background text-muted-foreground hover:bg-muted'}`}
                data-testid="day-mode-statement"
              >
                <Eye className="h-3 w-3 inline mr-1" />Statement
              </button>
            </div>
            <div className="relative ml-2">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input value={empFilter} onChange={e => setEmpFilter(e.target.value)}
                placeholder="Filter employees..."
                className="rounded-sm pl-7 h-8 w-48 text-sm" data-testid="day-employee-search" />
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

        {isStatement ? renderDailyStatement(dayNum) : (
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
                    const s1=getVal(emp.id,'st_r1'), o1=getVal(emp.id,'ot_r1'), d1=getVal(emp.id,'dt_r1');
                    const s2=getVal(emp.id,'st_r2'), o2=getVal(emp.id,'ot_r2'), d2=getVal(emp.id,'dt_r2');
                    const sr=getVal(emp.id,'sr_hours');
                    const hrs = s1+o1+d1+s2+o2+d2;
                    const gross = calcGross(emp.rate1||0, emp.rate2||0, emp.special_rate||0, s1,o1,d1,s2,o2,d2,sr);
                    return (
                      <tr key={emp.id} className={i%2===0?'':'bg-muted/30'}>
                        <td className="font-mono text-xs text-muted-foreground">{i+1}</td>
                        <td className="text-sm font-medium max-w-[140px] truncate">{emp.name}</td>
                        <td className="text-xs text-muted-foreground">{emp.dept_emp_num}</td>
                        {hourFields.map((f, fi) => (
                          <td key={f} className={`p-0 ${f.includes('r2') ? 'r2-col' : ''}`}>
                            <input type="number" step="0.5" min="0" value={getVal(emp.id,f) || ''}
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
                      {hourFields.map(f => {
                        const total = employees.reduce((sum, emp) => sum + (timeEntries[emp.id]?.[f] || 0), 0);
                        return <td key={f} className={`font-mono text-xs text-right font-bold ${f.includes('r2') ? 'r2-col' : ''}`}>{total.toFixed(1)}</td>;
                      })}
                      <td className="font-mono text-xs text-right font-bold">
                        {employees.reduce((s, emp) => {
                          const te = timeEntries[emp.id] || {};
                          return s + (te.st_r1||0)+(te.ot_r1||0)+(te.dt_r1||0)+(te.st_r2||0)+(te.ot_r2||0)+(te.dt_r2||0);
                        }, 0).toFixed(1)}
                      </td>
                      <td className="font-mono text-xs text-right font-bold">
                        {$f(employees.reduce((s, emp) => {
                          const te = timeEntries[emp.id] || {};
                          return s + calcGross(emp.rate1||0,emp.rate2||0,emp.special_rate||0,te.st_r1||0,te.ot_r1||0,te.dt_r1||0,te.st_r2||0,te.ot_r2||0,te.dt_r2||0,te.sr_hours||0);
                        }, 0))}
                      </td>
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
  };

  const renderSummaryTab = () => {
    if (!summaryData) return <p className="p-4 text-muted-foreground text-sm">Loading summary...</p>;
    const emps = summaryData.employees || [];
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
                <tr key={emp.employee_id} className={i%2===0?'':'bg-muted/30'}>
                  <td className="font-mono text-xs text-muted-foreground">{i+1}</td>
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
                  {['r1_st','r1_ot','r1_dt'].map(k => (
                    <td key={k} className="font-mono text-xs text-right font-bold">{emps.reduce((s,e)=>s+(e[k]||0),0).toFixed(1)}</td>
                  ))}
                  <td></td>
                  {['r2_st','r2_ot','r2_dt'].map(k => (
                    <td key={k} className="font-mono text-xs text-right font-bold r2-col">{emps.reduce((s,e)=>s+(e[k]||0),0).toFixed(1)}</td>
                  ))}
                  <td></td>
                  <td className="font-mono text-xs text-right font-bold">{emps.reduce((s,e)=>s+(e.sr_hours||0),0).toFixed(1)}</td>
                  <td className="font-mono text-xs text-right font-bold">{$f(emps.reduce((s,e)=>s+(e.special_tot||0),0))}</td>
                  <td className="font-mono text-xs text-right font-bold">{emps.reduce((s,e)=>s+(e.total_hours||0),0).toFixed(1)}</td>
                  <td className="font-mono text-xs text-right font-bold">{$f(emps.reduce((s,e)=>s+(e.benefit_co||0),0))}</td>
                  <td className="font-mono text-xs text-right font-bold">{$f(emps.reduce((s,e)=>s+(e.fund_co||0),0))}</td>
                  <td className="font-mono text-xs text-right font-bold">{$f(emps.reduce((s,e)=>s+(e.deduction||0),0))}</td>
                  <td className="font-mono text-xs text-right font-bold">{$f(emps.reduce((s,e)=>s+(e.gross||0),0))}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-3 flex items-center justify-between sticky top-0 bg-background z-50">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" className="rounded-sm" onClick={() => navigate('/')} data-testid="back-button">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="font-heading text-lg font-bold tracking-tight">{event.event_name || 'Untitled Event'}</h1>
            <p className="text-xs text-muted-foreground">
              {[event.job_number && `#${event.job_number}`, event.employer].filter(Boolean).join(' / ')}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={() => handleExport('excel')} data-testid="header-export-excel">
            <FileSpreadsheet className="h-3 w-3" /> Excel
          </Button>
          <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={handleFullReportPdf} data-testid="header-export-full-pdf">
            <FileText className="h-3 w-3" /> Full Report
          </Button>
        </div>
      </header>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <div className="border-b border-border px-6 overflow-x-auto">
          <TabsList className="h-auto bg-transparent p-0 gap-0">
            <TabsTrigger value="info" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 text-xs tracking-wider uppercase font-semibold" data-testid="tab-info">
              Info
            </TabsTrigger>
            <TabsTrigger value="employees" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 text-xs tracking-wider uppercase font-semibold" data-testid="tab-employees">
              Employees ({employees.length})
            </TabsTrigger>
            {DAYS.map(d => (
              <TabsTrigger key={d} value={`day-${d}`} className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-3 py-2 text-xs tracking-wider uppercase font-semibold" data-testid={`tab-day-${d}`}>
                D{d}
              </TabsTrigger>
            ))}
            <TabsTrigger value="summary" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 text-xs tracking-wider uppercase font-semibold" data-testid="tab-summary">
              Summary
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="info" className="mt-0">{renderInfoTab()}</TabsContent>
        <TabsContent value="employees" className="mt-0">{renderEmployeesTab()}</TabsContent>
        {DAYS.map(d => (
          <TabsContent key={d} value={`day-${d}`} className="mt-0">{renderDayTab(d)}</TabsContent>
        ))}
        <TabsContent value="summary" className="mt-0">{renderSummaryTab()}</TabsContent>
      </Tabs>
    </div>
  );
}
