import { useState, useMemo } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { $f } from '../../lib/payroll';
import { Plus, Trash2, Pencil, Check, X, GripVertical, ArrowUpDown, ArrowUp, ArrowDown, Upload, Download, Search } from 'lucide-react';

function SortIndicator({ sortField, sortDir, field }) {
  if (sortField !== field) return <ArrowUpDown className="h-3 w-3 inline ml-1 opacity-40" />;
  if (sortDir === 'asc') return <ArrowUp className="h-3 w-3 inline ml-1 text-primary" />;
  return <ArrowDown className="h-3 w-3 inline ml-1 text-primary" />;
}

export default function EmployeesTab({
  employees, isEditor, empFilter, setEmpFilter,
  onAdd, onDelete, onStartEdit, onCancelEdit, onSaveEdit,
  editingEmp, editForm, setEditForm,
  newEmp, setNewEmp,
  onSort, sortField, sortDir,
  onDragStart, onDragOver, onDrop, dragIdx,
  onImportFile, onDownloadTemplate,
}) {
  const filtered = useMemo(() => {
    const q = empFilter.toLowerCase();
    return q ? employees.filter(e => e.name.toLowerCase().includes(q) || (e.dept_emp_num || '').toLowerCase().includes(q)) : employees;
  }, [employees, empFilter]);

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
          {empFilter && <span className="text-xs text-muted-foreground">{filtered.length} match{filtered.length !== 1 ? 'es' : ''}</span>}
        </div>
        {isEditor && (
        <div className="flex gap-2">
          <Button variant="outline" className="rounded-sm gap-2 text-sm" onClick={onDownloadTemplate} data-testid="download-template-button">
            <Download className="h-4 w-4" /> Template
          </Button>
          <label className="cursor-pointer">
            <input type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={onImportFile} data-testid="import-file-input" />
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
              <th className="text-left cursor-pointer select-none hover:text-primary transition-colors" onClick={() => onSort('name')} data-testid="sort-by-name">
                Name<SortIndicator sortField={sortField} sortDir={sortDir} field="name" />
              </th>
              <th className="text-left cursor-pointer select-none hover:text-primary transition-colors" onClick={() => onSort('dept_emp_num')} data-testid="sort-by-dept">
                Dept/Emp #<SortIndicator sortField={sortField} sortDir={sortDir} field="dept_emp_num" />
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
                  <td className="font-mono text-xs text-muted-foreground">{i + 1}</td>
                  <td className="p-0"><input type="text" value={editForm.name}
                    onChange={e => setEditForm(p => ({ ...p, name: e.target.value }))}
                    className="w-full px-2 py-1 text-sm border border-ring bg-background focus:outline-none" data-testid={`edit-name-${emp.id}`} /></td>
                  <td className="p-0"><input type="text" value={editForm.dept_emp_num}
                    onChange={e => setEditForm(p => ({ ...p, dept_emp_num: e.target.value }))}
                    className="w-full px-2 py-1 text-sm border border-ring bg-background focus:outline-none" data-testid={`edit-dept-${emp.id}`} /></td>
                  <td className="p-0"><input type="number" step="0.01" value={editForm.rate1}
                    onChange={e => setEditForm(p => ({ ...p, rate1: e.target.value }))}
                    className="w-full px-2 py-1 text-sm font-mono text-right border border-ring bg-background focus:outline-none" data-testid={`edit-rate1-${emp.id}`} /></td>
                  <td className="p-0"><input type="number" step="0.01" value={editForm.rate2}
                    onChange={e => setEditForm(p => ({ ...p, rate2: e.target.value }))}
                    className="w-full px-2 py-1 text-sm font-mono text-right border border-ring bg-background focus:outline-none" data-testid={`edit-rate2-${emp.id}`} /></td>
                  <td className="p-0"><input type="number" step="0.01" value={editForm.special_rate}
                    onChange={e => setEditForm(p => ({ ...p, special_rate: e.target.value }))}
                    className="w-full px-2 py-1 text-sm font-mono text-right border border-ring bg-background focus:outline-none" data-testid={`edit-sr-${emp.id}`} /></td>
                  <td className="text-center">
                    <div className="flex gap-1 justify-center">
                      <Button variant="ghost" size="icon" className="h-6 w-6 rounded-sm text-green-600 hover:text-green-700 hover:bg-green-50"
                        onClick={() => onSaveEdit(emp.id)} data-testid={`save-edit-${emp.id}`}>
                        <Check className="h-3 w-3" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-6 w-6 rounded-sm text-muted-foreground hover:text-foreground"
                        onClick={onCancelEdit} data-testid={`cancel-edit-${emp.id}`}>
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={emp.id}
                  draggable={isEditor}
                  onDragStart={() => isEditor && onDragStart(i)}
                  onDragOver={isEditor ? onDragOver : undefined}
                  onDrop={() => isEditor && onDrop(i)}
                  className={`${i % 2 === 0 ? '' : 'bg-muted/30'} ${dragIdx === i ? 'opacity-40' : ''} transition-opacity`}>
                  {isEditor ? (
                  <td className="cursor-grab active:cursor-grabbing px-1" data-testid={`drag-handle-${emp.id}`}>
                    <GripVertical className="h-3.5 w-3.5 text-muted-foreground" />
                  </td>
                  ) : <td></td>}
                  <td className="font-mono text-xs text-muted-foreground">{i + 1}</td>
                  <td>{emp.name}</td>
                  <td>{emp.dept_emp_num}</td>
                  <td className="text-right font-mono">{$f(emp.rate1)}</td>
                  <td className="text-right font-mono">{$f(emp.rate2)}</td>
                  <td className="text-right font-mono">{$f(emp.special_rate)}</td>
                  {isEditor && (
                  <td className="text-center">
                    <div className="flex gap-1 justify-center">
                      <Button variant="ghost" size="icon" className="h-6 w-6 rounded-sm text-muted-foreground hover:text-primary"
                        onClick={() => onStartEdit(emp)} data-testid={`edit-emp-${emp.id}`}>
                        <Pencil className="h-3 w-3" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-6 w-6 rounded-sm text-muted-foreground hover:text-destructive"
                        onClick={() => onDelete(emp.id)} data-testid={`delete-emp-${emp.id}`}>
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
      <form onSubmit={onAdd} className="mt-4 flex gap-2 items-end border-t border-border pt-4">
        <div className="flex-1">
          <Label className="text-xs text-muted-foreground">Name</Label>
          <Input value={newEmp.name} onChange={e => setNewEmp(p => ({ ...p, name: e.target.value }))}
            placeholder="Employee name" required className="rounded-sm" data-testid="new-emp-name" />
        </div>
        <div className="w-28">
          <Label className="text-xs text-muted-foreground">Dept/Emp#</Label>
          <Input value={newEmp.dept_emp_num} onChange={e => setNewEmp(p => ({ ...p, dept_emp_num: e.target.value }))}
            placeholder="Dept#" className="rounded-sm" data-testid="new-emp-dept" />
        </div>
        <div className="w-24">
          <Label className="text-xs text-muted-foreground">Rate 1</Label>
          <Input type="number" step="0.01" value={newEmp.rate1} onChange={e => setNewEmp(p => ({ ...p, rate1: e.target.value }))}
            placeholder="0.00" className="rounded-sm font-mono" data-testid="new-emp-rate1" />
        </div>
        <div className="w-24">
          <Label className="text-xs text-muted-foreground">Rate 2</Label>
          <Input type="number" step="0.01" value={newEmp.rate2} onChange={e => setNewEmp(p => ({ ...p, rate2: e.target.value }))}
            placeholder="0.00" className="rounded-sm font-mono" data-testid="new-emp-rate2" />
        </div>
        <div className="w-24">
          <Label className="text-xs text-muted-foreground">SR</Label>
          <Input type="number" step="0.01" value={newEmp.special_rate} onChange={e => setNewEmp(p => ({ ...p, special_rate: e.target.value }))}
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
  );
}
