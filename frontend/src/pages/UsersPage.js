import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { toast } from 'sonner';
import { Plus, ArrowLeft, Trash2, Pencil, Check, X, Shield, Eye, UserCheck, LogOut } from 'lucide-react';

export default function UsersPage() {
  const { user: currentUser, logout } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'viewer' });
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});

  useEffect(() => { loadUsers(); }, []);

  const loadUsers = async () => {
    try {
      const res = await api.get('/users');
      setUsers(res.data);
    } catch { toast.error('Failed to load users'); }
    finally { setLoading(false); }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      const res = await api.post('/users', form);
      setUsers(prev => [res.data, ...prev]);
      setOpen(false);
      setForm({ name: '', email: '', password: '', role: 'viewer' });
      toast.success('User created');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create user');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this user?')) return;
    try {
      await api.delete(`/users/${id}`);
      setUsers(prev => prev.filter(u => u.id !== id));
      toast.success('User deleted');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete');
    }
  };

  const startEdit = (u) => {
    setEditingId(u.id);
    setEditForm({ name: u.name, email: u.email, role: u.role, password: '' });
  };

  const saveEdit = async (id) => {
    try {
      const payload = { name: editForm.name, email: editForm.email, role: editForm.role };
      if (editForm.password) payload.password = editForm.password;
      const res = await api.put(`/users/${id}`, payload);
      setUsers(prev => prev.map(u => u.id === id ? res.data : u));
      setEditingId(null);
      toast.success('User updated');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update');
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-3 flex items-center justify-between sticky top-0 bg-background z-50">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" className="rounded-sm" onClick={() => navigate('/')} data-testid="back-to-events">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="font-heading text-2xl font-black tracking-tight">MEBO</h1>
          <span className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">User Management</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">{currentUser?.email}</span>
          <Button variant="ghost" size="sm" onClick={logout} data-testid="logout-button" className="rounded-sm">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </header>

      <main className="p-6 max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="font-heading text-2xl font-bold tracking-tight">Users</h2>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button data-testid="create-user-button" className="rounded-sm gap-2">
                <Plus className="h-4 w-4" /> Add User
              </Button>
            </DialogTrigger>
            <DialogContent className="rounded-sm">
              <DialogHeader>
                <DialogTitle className="font-heading font-bold">Create User</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreate} className="space-y-3 mt-2">
                <div>
                  <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Name</Label>
                  <Input value={form.name} onChange={e => setForm(p => ({...p, name: e.target.value}))}
                    placeholder="Full name" className="mt-1 rounded-sm" data-testid="create-user-name" />
                </div>
                <div>
                  <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Email</Label>
                  <Input type="email" value={form.email} onChange={e => setForm(p => ({...p, email: e.target.value}))}
                    placeholder="user@example.com" required className="mt-1 rounded-sm" data-testid="create-user-email" />
                </div>
                <div>
                  <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Password</Label>
                  <Input type="password" value={form.password} onChange={e => setForm(p => ({...p, password: e.target.value}))}
                    placeholder="Password" required className="mt-1 rounded-sm" data-testid="create-user-password" />
                </div>
                <div>
                  <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Role</Label>
                  <Select value={form.role} onValueChange={v => setForm(p => ({...p, role: v}))}>
                    <SelectTrigger className="mt-1 rounded-sm" data-testid="create-user-role">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="admin">Admin (Full Access + User Mgmt)</SelectItem>
                      <SelectItem value="user">User (Full Access)</SelectItem>
                      <SelectItem value="viewer">Viewer (Read Only)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <Button type="submit" className="w-full rounded-sm" data-testid="create-user-submit">Create User</Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {loading ? (
          <p className="text-muted-foreground text-sm">Loading users...</p>
        ) : (
          <div className="border border-border divide-y divide-border" data-testid="users-list">
            {users.map(u => (
              editingId === u.id ? (
                <div key={u.id} className="px-4 py-3 bg-primary/5 space-y-2">
                  <div className="grid grid-cols-4 gap-2">
                    <Input value={editForm.name} onChange={e => setEditForm(p => ({...p, name: e.target.value}))}
                      placeholder="Name" className="rounded-sm text-sm" data-testid={`edit-user-name-${u.id}`} />
                    <Input value={editForm.email} onChange={e => setEditForm(p => ({...p, email: e.target.value}))}
                      placeholder="Email" className="rounded-sm text-sm" data-testid={`edit-user-email-${u.id}`} />
                    <Input type="password" value={editForm.password} onChange={e => setEditForm(p => ({...p, password: e.target.value}))}
                      placeholder="New password (optional)" className="rounded-sm text-sm" data-testid={`edit-user-password-${u.id}`} />
                    <Select value={editForm.role} onValueChange={v => setEditForm(p => ({...p, role: v}))}>
                      <SelectTrigger className="rounded-sm text-sm" data-testid={`edit-user-role-${u.id}`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                      <SelectItem value="admin">Admin</SelectItem>
                      <SelectItem value="user">User</SelectItem>
                      <SelectItem value="viewer">Viewer</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" className="rounded-sm gap-1" onClick={() => saveEdit(u.id)} data-testid={`save-user-${u.id}`}>
                      <Check className="h-3 w-3" /> Save
                    </Button>
                    <Button size="sm" variant="ghost" className="rounded-sm gap-1" onClick={() => setEditingId(null)} data-testid={`cancel-user-${u.id}`}>
                      <X className="h-3 w-3" /> Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <div key={u.id} className="flex items-center justify-between px-4 py-3" data-testid={`user-row-${u.id}`}>
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-sm flex items-center justify-center ${u.role === 'admin' ? 'bg-primary/10 text-primary' : u.role === 'user' ? 'bg-green-50 text-green-600' : 'bg-muted text-muted-foreground'}`}>
                      {u.role === 'admin' ? <Shield className="h-4 w-4" /> : u.role === 'user' ? <UserCheck className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </div>
                    <div>
                      <p className="text-sm font-semibold">{u.name || u.email}</p>
                      <p className="text-xs text-muted-foreground">{u.email} <span className="ml-2 inline-block px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider border border-border rounded-sm">{u.role}</span></p>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" className="h-7 w-7 rounded-sm text-muted-foreground hover:text-primary"
                      onClick={() => startEdit(u)} data-testid={`edit-user-btn-${u.id}`}>
                      <Pencil className="h-3 w-3" />
                    </Button>
                    {u.id !== currentUser?.id && (
                      <Button variant="ghost" size="icon" className="h-7 w-7 rounded-sm text-muted-foreground hover:text-destructive"
                        onClick={() => handleDelete(u.id)} data-testid={`delete-user-btn-${u.id}`}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
                </div>
              )
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
