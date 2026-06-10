import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { toast } from 'sonner';
import { LogOut, ArrowLeft, Users, BarChart3, Mail, Building2, Briefcase, MessageSquare, Search, Trash2, Download } from 'lucide-react';

export default function WaitlistPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');

  const isAdmin = user?.role === 'admin';

  useEffect(() => {
    if (user && !isAdmin) navigate('/app');
  }, [user, isAdmin, navigate]);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/waitlist');
        setEntries(res.data.entries || []);
      } catch { toast.error('Failed to load waitlist'); }
      finally { setLoading(false); }
    })();
  }, []);

  const handleDelete = async (email) => {
    if (!window.confirm(`Remove ${email} from waitlist?`)) return;
    try {
      await api.delete(`/waitlist/${encodeURIComponent(email)}`);
      setEntries(prev => prev.filter(e => e.email !== email));
      toast.success('Removed from waitlist');
    } catch { toast.error('Failed to remove'); }
  };

  const handleExport = () => {
    const headers = ['Email', 'Company', 'Role', 'Message', 'Created At', 'IP'];
    const rows = filtered.map(e => [e.email, e.company || '', e.role || '', (e.message || '').replace(/\n/g, ' '), e.created_at || '', e.ip || '']);
    const csv = [headers, ...rows].map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `waitlist_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Waitlist exported');
  };

  const q = filter.toLowerCase();
  const filtered = entries.filter(e =>
    !q ||
    (e.email || '').toLowerCase().includes(q) ||
    (e.company || '').toLowerCase().includes(q) ||
    (e.role || '').toLowerCase().includes(q) ||
    (e.message || '').toLowerCase().includes(q)
  );

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-3 flex items-center justify-between sticky top-0 bg-background z-50">
        <div className="flex items-center gap-4">
          <h1 className="font-heading text-2xl font-black tracking-tight">MEBO</h1>
          <span className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Waitlist</span>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate('/app')} className="rounded-sm gap-2 text-xs">
            <ArrowLeft className="h-4 w-4" /> Events
          </Button>
          <Button variant="ghost" size="sm" onClick={() => navigate('/dashboard')} className="rounded-sm gap-2 text-xs">
            <BarChart3 className="h-4 w-4" /> Dashboard
          </Button>
          <Button variant="ghost" size="sm" onClick={() => navigate('/users')} className="rounded-sm gap-2 text-xs">
            <Users className="h-4 w-4" /> Users
          </Button>
          <span className="text-sm text-muted-foreground">{user?.email}</span>
          <Button variant="ghost" size="sm" onClick={logout} data-testid="logout-button" className="rounded-sm">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </header>

      <main className="p-6 max-w-6xl mx-auto" data-testid="waitlist-page">
        <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
          <div>
            <h2 className="font-heading text-2xl font-bold tracking-tight">Waitlist Signups</h2>
            <p className="text-xs text-muted-foreground mt-1">
              {loading ? 'Loading...' : `${entries.length} total signup${entries.length === 1 ? '' : 's'}`}
              {filter && ` · ${filtered.length} match${filtered.length === 1 ? '' : 'es'} "${filter}"`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="h-3.5 w-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={filter}
                onChange={e => setFilter(e.target.value)}
                placeholder="Search email, company, role..."
                className="rounded-sm h-9 pl-8 w-64"
                data-testid="waitlist-search-input"
              />
            </div>
            <Button onClick={handleExport} disabled={entries.length === 0} className="rounded-sm gap-2" data-testid="waitlist-export-csv-button">
              <Download className="h-4 w-4" /> Export CSV
            </Button>
          </div>
        </div>

        {loading ? (
          <p className="text-muted-foreground text-sm">Loading...</p>
        ) : entries.length === 0 ? (
          <div className="border border-dashed border-border p-12 text-center" data-testid="waitlist-empty-state">
            <Mail className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <p className="font-heading font-bold text-base mb-1">No signups yet</p>
            <p className="text-sm text-muted-foreground">Once people start joining your waitlist, they&apos;ll appear here.</p>
            <p className="text-xs text-muted-foreground mt-4">
              Share <code className="px-1.5 py-0.5 bg-muted rounded-sm">https://mebopayroll.com</code> to start collecting signups.
            </p>
          </div>
        ) : filtered.length === 0 ? (
          <p className="text-muted-foreground text-sm">No signups match &quot;{filter}&quot;.</p>
        ) : (
          <div className="space-y-3" data-testid="waitlist-entries-list">
            {filtered.map((e, i) => (
              <div key={e.email} className="border border-border p-4 bg-background hover:border-primary/40 transition-colors" data-testid={`waitlist-entry-${i}`}>
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mb-2">
                      <a href={`mailto:${e.email}`} className="font-heading font-bold text-base flex items-center gap-2 hover:text-primary transition-colors">
                        <Mail className="h-4 w-4 text-muted-foreground" />
                        {e.email}
                      </a>
                      <span className="text-[10px] tracking-wider uppercase text-muted-foreground font-mono">
                        {e.created_at ? new Date(e.created_at).toLocaleString() : ''}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
                      {e.company && (
                        <span className="flex items-center gap-1.5 text-muted-foreground">
                          <Building2 className="h-3.5 w-3.5" /> {e.company}
                        </span>
                      )}
                      {e.role && (
                        <span className="flex items-center gap-1.5 text-muted-foreground">
                          <Briefcase className="h-3.5 w-3.5" /> {e.role}
                        </span>
                      )}
                    </div>
                    {e.message && (
                      <div className="mt-3 text-sm border-l-2 border-border pl-3 py-1 flex gap-2 text-muted-foreground">
                        <MessageSquare className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
                        <span className="whitespace-pre-wrap">{e.message}</span>
                      </div>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="rounded-sm text-muted-foreground hover:text-destructive flex-shrink-0"
                    onClick={() => handleDelete(e.email)}
                    data-testid={`delete-waitlist-${i}`}
                    title="Remove from waitlist"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
