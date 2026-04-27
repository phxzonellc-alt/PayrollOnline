import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import '@/App.css';
import { Button } from '../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { toast } from 'sonner';
import { ArrowLeft, FileSpreadsheet, FileText, LogOut, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { DAYS } from '../lib/payroll';
import InfoTab from '../components/payroll/InfoTab';
import EmployeesTab from '../components/payroll/EmployeesTab';
import DayTab from '../components/payroll/DayTab';
import SummaryTab from '../components/payroll/SummaryTab';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';

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

  // ---- Data loading ----
  const loadEvent = useCallback(async () => {
    try {
      const res = await api.get(`/events/${id}`);
      setEvent(res.data);
    } catch (err) {
      console.error('Failed to load event:', err);
      toast.error('Failed to load event');
      navigate('/');
    }
  }, [id, navigate]);

  const loadEmployees = useCallback(async () => {
    try {
      const res = await api.get(`/events/${id}/employees`);
      setEmployees(res.data);
    } catch (err) { console.error('Failed to load employees:', err); toast.error('Failed to load employees'); }
  }, [id]);

  const loadTimeEntries = useCallback(async (day) => {
    try {
      const res = await api.get(`/events/${id}/time-entries?day=${day}`);
      const map = {};
      res.data.forEach(e => { map[e.employee_id] = e; });
      setTimeEntries(map);
    } catch (err) { console.error('Failed to load time entries:', err); toast.error('Failed to load time entries'); }
  }, [id]);

  const loadSummary = useCallback(async () => {
    try {
      const res = await api.get(`/events/${id}/sum-totals`);
      setSummaryData(res.data);
    } catch (err) { console.error('Failed to load summary:', err); toast.error('Failed to load summary'); }
  }, [id]);

  const loadDailyStatement = useCallback(async (day) => {
    try {
      const res = await api.get(`/events/${id}/daily-statement/${day}`);
      setDailyStatement(res.data);
    } catch (err) { console.error('Failed to load daily statement:', err); toast.error('Failed to load daily statement'); }
  }, [id]);

  // ---- Lifecycle ----
  useEffect(() => {
    Promise.all([loadEvent(), loadEmployees()]).finally(() => setLoading(false));
  }, [loadEvent, loadEmployees]);

  useEffect(() => { timeEntriesRef.current = timeEntries; }, [timeEntries]);
  useEffect(() => { employeesRef.current = employees; }, [employees]);
  useEffect(() => { eventRef.current = event; }, [event]);

  // ---- Silent save helpers ----
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
    try { await api.post(`/events/${id}/time-entries/batch`, { entries }); }
    catch (err) { console.error('Auto-save day failed:', err); }
    dayDirtyRef.current = false;
  }, [id]);

  const silentSaveInfo = useCallback(async () => {
    if (!infoDirtyRef.current || !eventRef.current) return;
    try { await api.put(`/events/${id}`, eventRef.current); }
    catch (err) { console.error('Auto-save info failed:', err); }
    infoDirtyRef.current = false;
  }, [id]);

  const handleTabChange = useCallback(async (newTab) => {
    const prev = prevTabRef.current;
    if (prev === newTab) return;
    if (prev === 'info') await silentSaveInfo();
    else if (prev.startsWith('day-')) await silentSaveDay(prev);
    prevTabRef.current = newTab;
    setActiveTab(newTab);
  }, [silentSaveInfo, silentSaveDay]);

  // Auto-save on unmount
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

  // Load tab data on switch
  useEffect(() => {
    if (activeTab.startsWith('day-')) {
      const dayNum = parseInt(activeTab.split('-')[1]);
      loadTimeEntries(dayNum);
      if (dayViewMode === 'statement') loadDailyStatement(dayNum);
    } else if (activeTab === 'summary') {
      loadSummary();
    }
  }, [activeTab, loadTimeEntries, loadSummary, loadDailyStatement, dayViewMode]);

  // ---- Event handlers ----
  const updateEventField = useCallback((updater) => {
    infoDirtyRef.current = true;
    setEvent(updater);
  }, []);

  const saveEvent = useCallback(async () => {
    setSaving(true);
    try {
      const res = await api.put(`/events/${id}`, event);
      setEvent(res.data);
      infoDirtyRef.current = false;
      toast.success('Event saved');
    } catch (err) { console.error('Save event failed:', err); toast.error('Failed to save'); }
    finally { setSaving(false); }
  }, [id, event]);

  const addEmployee = useCallback(async (e) => {
    e.preventDefault();
    try {
      const res = await api.post(`/events/${id}/employees`, {
        ...newEmp, rate1: parseFloat(newEmp.rate1) || 0,
        rate2: parseFloat(newEmp.rate2) || 0, special_rate: parseFloat(newEmp.special_rate) || 0
      });
      setEmployees(prev => [...prev, res.data]);
      setNewEmp({ name: '', dept_emp_num: '', rate1: '', rate2: '', special_rate: '' });
      toast.success('Employee added');
    } catch (err) { console.error('Add employee failed:', err); toast.error('Failed to add employee'); }
  }, [id, newEmp]);

  const deleteEmployee = useCallback(async (empId) => {
    if (!window.confirm('Delete this employee?')) return;
    try {
      await api.delete(`/events/${id}/employees/${empId}`);
      setEmployees(prev => prev.filter(e => e.id !== empId));
      toast.success('Employee deleted');
    } catch (err) { console.error('Delete employee failed:', err); toast.error('Failed to delete'); }
  }, [id]);

  const startEdit = useCallback((emp) => {
    setEditingEmp(emp.id);
    setEditForm({ name: emp.name, dept_emp_num: emp.dept_emp_num, rate1: emp.rate1, rate2: emp.rate2, special_rate: emp.special_rate });
  }, []);

  const cancelEdit = useCallback(() => { setEditingEmp(null); setEditForm({}); }, []);

  const saveEdit = useCallback(async (empId) => {
    try {
      const res = await api.put(`/events/${id}/employees/${empId}`, {
        name: editForm.name, dept_emp_num: editForm.dept_emp_num,
        rate1: parseFloat(editForm.rate1) || 0, rate2: parseFloat(editForm.rate2) || 0,
        special_rate: parseFloat(editForm.special_rate) || 0,
      });
      setEmployees(prev => prev.map(e => e.id === empId ? res.data : e));
      setEditingEmp(null);
      toast.success('Employee updated');
    } catch (err) { console.error('Save edit failed:', err); toast.error('Failed to update'); }
  }, [id, editForm]);

  const [importReport, setImportReport] = useState(null);

  const handleImportFile = useCallback(async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await api.post(`/events/${id}/employees/import`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      setEmployees(prev => [...prev, ...res.data.employees]);
      const { imported, skipped, errors = [], warnings = [] } = res.data;
      if (skipped === 0 && warnings.length === 0) {
        toast.success(`Imported ${imported} employees`);
      } else {
        // Open detailed report for the user
        setImportReport({ imported, skipped, errors, warnings });
        if (imported > 0) {
          toast.success(`Imported ${imported}, ${skipped} skipped`);
        } else {
          toast.error(`Import failed: ${skipped} row${skipped !== 1 ? 's' : ''} had issues`);
        }
      }
    } catch (err) {
      console.error('Import failed:', err);
      const msg = err?.response?.data?.detail || 'Import failed';
      toast.error(msg);
    }
    e.target.value = '';
  }, [id]);

  const handleDownloadTemplate = useCallback(async () => {
    try {
      const url = `${process.env.REACT_APP_BACKEND_URL}/api/employees/template`;
      const res = await fetch(url, { credentials: 'include' });
      const blob = await res.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'employee_import_template.csv';
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (err) { console.error('Template download failed:', err); toast.error('Failed to download template'); }
  }, []);

  const handleDayStatementPdf = useCallback(async (dayNum) => {
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
    } catch (err) { console.error('Day statement PDF failed:', err); toast.error('PDF export failed'); }
  }, [id, event?.event_name]);

  const handleFullReportPdf = useCallback(async () => {
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
    } catch (err) { console.error('Full report failed:', err); toast.error('Full report export failed'); }
  }, [id, event?.event_name]);

  const updateHour = useCallback((empId, field, value) => {
    dayDirtyRef.current = true;
    setTimeEntries(prev => ({
      ...prev,
      [empId]: { ...(prev[empId] || {}), employee_id: empId, [field]: parseFloat(value) || 0 }
    }));
  }, []);

  const fillColumn = useCallback((field, value, scope = 'all') => {
    const num = parseFloat(value) || 0;
    dayDirtyRef.current = true;
    const targets = scope === 'filtered'
      ? employees.filter(e => {
          const q = empFilter.toLowerCase();
          return !q || e.name.toLowerCase().includes(q) || (e.dept_emp_num || '').toLowerCase().includes(q);
        })
      : employees;
    setTimeEntries(prev => {
      const next = { ...prev };
      targets.forEach(emp => {
        next[emp.id] = { ...(next[emp.id] || {}), employee_id: emp.id, [field]: num };
      });
      return next;
    });
  }, [employees, empFilter]);

  const copyFromDay = useCallback(async (sourceDay) => {
    const dayNum = parseInt(activeTab.split('-')[1]);
    if (sourceDay === dayNum) {
      toast.error('Choose a different day to copy from');
      return;
    }
    try {
      const res = await api.get(`/events/${id}/time-entries?day=${sourceDay}`);
      const map = {};
      res.data.forEach(e => {
        map[e.employee_id] = {
          employee_id: e.employee_id,
          st_r1: e.st_r1 || 0, ot_r1: e.ot_r1 || 0, dt_r1: e.dt_r1 || 0,
          st_r2: e.st_r2 || 0, ot_r2: e.ot_r2 || 0, dt_r2: e.dt_r2 || 0,
          sr_hours: e.sr_hours || 0,
        };
      });
      // Ensure every employee has a record (so Save Day clears any rows that source-day didn't have)
      employees.forEach(emp => {
        if (!map[emp.id]) {
          map[emp.id] = { employee_id: emp.id, st_r1: 0, ot_r1: 0, dt_r1: 0, st_r2: 0, ot_r2: 0, dt_r2: 0, sr_hours: 0 };
        }
      });
      setTimeEntries(map);
      dayDirtyRef.current = true;
      const filledCount = Object.values(map).filter(e =>
        (e.st_r1 + e.ot_r1 + e.dt_r1 + e.st_r2 + e.ot_r2 + e.dt_r2 + e.sr_hours) > 0
      ).length;
      toast.success(`Copied from Day ${sourceDay} (${filledCount} with hours). Click Save Day to commit.`);
    } catch (err) {
      console.error('Copy day failed:', err);
      toast.error('Failed to copy');
    }
  }, [id, activeTab, employees]);

  const saveDay = useCallback(async () => {
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
      dayDirtyRef.current = false;
      toast.success(`Day ${dayNum} saved`);
    } catch (err) { console.error('Save day failed:', err); toast.error('Failed to save'); }
    finally { setSaving(false); }
  }, [id, activeTab, employees, timeEntries]);

  const handleExport = useCallback(async (type) => {
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
    } catch (err) { console.error('Export failed:', err); toast.error('Export failed'); }
  }, [id, event?.event_name]);

  // ---- Drag & Sort ----
  const handleDragStart = useCallback((idx) => { setDragIdx(idx); }, []);
  const handleDragOver = useCallback((e) => { e.preventDefault(); }, []);
  const handleDrop = useCallback(async (dropIdx) => {
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
    } catch (err) { console.error('Reorder failed:', err); toast.error('Failed to save order'); }
  }, [id, dragIdx, employees]);

  const handleSort = useCallback(async (field) => {
    let newDir, newField;
    if (sortField === field) {
      if (sortDir === 'asc') { newDir = 'desc'; newField = field; }
      else { newDir = 'asc'; newField = null; }
    } else {
      newDir = 'asc'; newField = field;
    }
    setSortField(newField);
    setSortDir(newDir);
    if (!newField) { await loadEmployees(); return; }
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
    } catch (err) { console.error('Sort failed:', err); toast.error('Failed to save order'); }
  }, [id, sortField, sortDir, employees, loadEmployees]);

  // ---- Loading state ----
  if (loading || !event) {
    return <div className="min-h-screen bg-background flex items-center justify-center"><p className="text-muted-foreground">Loading...</p></div>;
  }

  const fp = event.fund_pct || 0.02;
  const bp = event.benefit_pct || 0.21;
  const dp = event.deduction_pct || 0.05;

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
          <Button variant="ghost" size="sm" onClick={logout} data-testid="logout-button" className="rounded-sm ml-2">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </header>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <div className="border-b border-border px-6 overflow-x-auto">
          <TabsList className="h-auto bg-transparent p-0 gap-0">
            <TabsTrigger value="info" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 text-xs tracking-wider uppercase font-semibold" data-testid="tab-info">Info</TabsTrigger>
            <TabsTrigger value="employees" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 text-xs tracking-wider uppercase font-semibold" data-testid="tab-employees">Employees ({employees.length})</TabsTrigger>
            {DAYS.map(d => (
              <TabsTrigger key={d} value={`day-${d}`} className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-3 py-2 text-xs tracking-wider uppercase font-semibold" data-testid={`tab-day-${d}`}>D{d}</TabsTrigger>
            ))}
            <TabsTrigger value="summary" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 text-xs tracking-wider uppercase font-semibold" data-testid="tab-summary">Summary</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="info" className="mt-0">
          <InfoTab event={event} updateEventField={updateEventField} saveEvent={saveEvent} saving={saving} isEditor={isEditor} />
        </TabsContent>
        <TabsContent value="employees" className="mt-0">
          <EmployeesTab employees={employees} isEditor={isEditor} empFilter={empFilter} setEmpFilter={setEmpFilter}
            onAdd={addEmployee} onDelete={deleteEmployee} onStartEdit={startEdit} onCancelEdit={cancelEdit} onSaveEdit={saveEdit}
            editingEmp={editingEmp} editForm={editForm} setEditForm={setEditForm} newEmp={newEmp} setNewEmp={setNewEmp}
            onSort={handleSort} sortField={sortField} sortDir={sortDir}
            onDragStart={handleDragStart} onDragOver={handleDragOver} onDrop={handleDrop} dragIdx={dragIdx}
            onImportFile={handleImportFile} onDownloadTemplate={handleDownloadTemplate} />
        </TabsContent>
        {DAYS.map(d => (
          <TabsContent key={d} value={`day-${d}`} className="mt-0">
            <DayTab dayNum={d} event={event} employees={employees} timeEntries={timeEntries}
              updateHour={updateHour} saveDay={saveDay} saving={saving}
              fillColumn={fillColumn} copyFromDay={copyFromDay}
              dayViewMode={dayViewMode} setDayViewMode={setDayViewMode}
              loadDailyStatement={loadDailyStatement} dailyStatement={dailyStatement}
              handleDayStatementPdf={handleDayStatementPdf}
              empFilter={empFilter} setEmpFilter={setEmpFilter} fp={fp} bp={bp} dp={dp} isEditor={isEditor} />
          </TabsContent>
        ))}
        <TabsContent value="summary" className="mt-0">
          <SummaryTab summaryData={summaryData} handleExport={handleExport} handleFullReportPdf={handleFullReportPdf} />
        </TabsContent>
      </Tabs>

      <Dialog open={!!importReport} onOpenChange={(o) => !o && setImportReport(null)}>
        <DialogContent className="rounded-sm max-w-2xl max-h-[80vh] overflow-y-auto" data-testid="import-report-dialog">
          <DialogHeader>
            <DialogTitle className="font-heading font-bold flex items-center gap-2">
              {importReport?.imported > 0 ? (
                <CheckCircle2 className="h-5 w-5 text-primary" />
              ) : (
                <AlertTriangle className="h-5 w-5 text-destructive" />
              )}
              Import Report
            </DialogTitle>
          </DialogHeader>
          {importReport && (
            <div className="space-y-4 mt-2">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="border border-border p-3">
                  <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">Imported</p>
                  <p className="font-heading text-2xl font-black">{importReport.imported}</p>
                </div>
                <div className="border border-border p-3">
                  <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">Skipped</p>
                  <p className={`font-heading text-2xl font-black ${importReport.skipped > 0 ? 'text-destructive' : ''}`}>{importReport.skipped}</p>
                </div>
              </div>

              {importReport.errors.length > 0 && (
                <div data-testid="import-errors-list">
                  <p className="text-xs tracking-[0.2em] uppercase font-semibold text-destructive mb-2">Errors (rows skipped)</p>
                  <div className="border border-border max-h-60 overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-muted">
                        <tr className="border-b border-border">
                          <th className="text-left px-3 py-2 w-16">Row</th>
                          <th className="text-left px-3 py-2 w-40">Name</th>
                          <th className="text-left px-3 py-2">Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {importReport.errors.map((e, i) => (
                          <tr key={i} className="border-b border-border last:border-b-0">
                            <td className="px-3 py-2 font-mono text-muted-foreground">{e.row}</td>
                            <td className="px-3 py-2 font-medium">{e.name || <span className="text-muted-foreground italic">empty</span>}</td>
                            <td className="px-3 py-2 text-destructive">{e.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {importReport.warnings.length > 0 && (
                <div data-testid="import-warnings-list">
                  <p className="text-xs tracking-[0.2em] uppercase font-semibold text-amber-600 mb-2">Warnings (imported with caveats)</p>
                  <div className="border border-border max-h-40 overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-muted">
                        <tr className="border-b border-border">
                          <th className="text-left px-3 py-2 w-16">Row</th>
                          <th className="text-left px-3 py-2 w-40">Name</th>
                          <th className="text-left px-3 py-2">Note</th>
                        </tr>
                      </thead>
                      <tbody>
                        {importReport.warnings.map((w, i) => (
                          <tr key={i} className="border-b border-border last:border-b-0">
                            <td className="px-3 py-2 font-mono text-muted-foreground">{w.row}</td>
                            <td className="px-3 py-2 font-medium">{w.name}</td>
                            <td className="px-3 py-2">{w.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div className="flex justify-end pt-2">
                <Button onClick={() => setImportReport(null)} className="rounded-sm" data-testid="import-report-close-button">Close</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
