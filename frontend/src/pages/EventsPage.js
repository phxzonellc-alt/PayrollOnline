import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { toast } from 'sonner';
import { Plus, FileSpreadsheet, LogOut, Trash2 } from 'lucide-react';

export default function EventsPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ event_name: '', employer: '', job_number: '', venue: '' });

  useEffect(() => { loadEvents(); }, []);

  const loadEvents = async () => {
    try {
      const res = await api.get('/events');
      setEvents(res.data);
    } catch { toast.error('Failed to load events'); }
    finally { setLoading(false); }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      const res = await api.post('/events', form);
      setEvents(prev => [res.data, ...prev]);
      setOpen(false);
      setForm({ event_name: '', employer: '', job_number: '', venue: '' });
      toast.success('Event created');
      navigate(`/events/${res.data.id}`);
    } catch { toast.error('Failed to create event'); }
  };

  const handleDelete = async (id, e) => {
    e.stopPropagation();
    if (!window.confirm('Delete this event and all its data?')) return;
    try {
      await api.delete(`/events/${id}`);
      setEvents(prev => prev.filter(ev => ev.id !== id));
      toast.success('Event deleted');
    } catch { toast.error('Failed to delete'); }
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-6 py-3 flex items-center justify-between sticky top-0 bg-background z-50">
        <div className="flex items-center gap-4">
          <h1 className="font-heading text-2xl font-black tracking-tight">MEBO</h1>
          <span className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Payroll</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">{user?.email}</span>
          <Button variant="ghost" size="sm" onClick={logout} data-testid="logout-button" className="rounded-sm">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </header>

      <main className="p-6 max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="font-heading text-2xl font-bold tracking-tight">Events</h2>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button data-testid="create-event-button" className="rounded-sm gap-2">
                <Plus className="h-4 w-4" /> New Event
              </Button>
            </DialogTrigger>
            <DialogContent className="rounded-sm">
              <DialogHeader>
                <DialogTitle className="font-heading font-bold">Create Event</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreate} className="space-y-3 mt-2">
                <div>
                  <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Event Name</Label>
                  <Input value={form.event_name} onChange={e => setForm(p => ({...p, event_name: e.target.value}))}
                    placeholder="Event name" required className="mt-1 rounded-sm" data-testid="create-event-name" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Job Number</Label>
                    <Input value={form.job_number} onChange={e => setForm(p => ({...p, job_number: e.target.value}))}
                      placeholder="Job #" className="mt-1 rounded-sm" data-testid="create-event-job" />
                  </div>
                  <div>
                    <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Employer</Label>
                    <Input value={form.employer} onChange={e => setForm(p => ({...p, employer: e.target.value}))}
                      placeholder="Employer" className="mt-1 rounded-sm" data-testid="create-event-employer" />
                  </div>
                </div>
                <div>
                  <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Venue</Label>
                  <Input value={form.venue} onChange={e => setForm(p => ({...p, venue: e.target.value}))}
                    placeholder="Venue" className="mt-1 rounded-sm" data-testid="create-event-venue" />
                </div>
                <Button type="submit" className="w-full rounded-sm" data-testid="create-event-submit">Create</Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {loading ? (
          <p className="text-muted-foreground text-sm">Loading events...</p>
        ) : events.length === 0 ? (
          <div className="border border-dashed border-border p-12 text-center">
            <FileSpreadsheet className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground text-sm">No events yet. Create your first payroll event.</p>
          </div>
        ) : (
          <div className="border border-border divide-y divide-border" data-testid="event-list">
            {events.map(ev => (
              <div key={ev.id} onClick={() => navigate(`/events/${ev.id}`)}
                className="flex items-center justify-between px-4 py-3 hover:bg-muted cursor-pointer transition-colors duration-200"
                data-testid={`event-card-${ev.id}`}>
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-primary/10 flex items-center justify-center rounded-sm">
                    <FileSpreadsheet className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <p className="font-semibold text-sm">{ev.event_name || 'Untitled Event'}</p>
                    <p className="text-xs text-muted-foreground">
                      {[ev.job_number && `#${ev.job_number}`, ev.employer, ev.venue].filter(Boolean).join(' / ')}
                    </p>
                  </div>
                </div>
                <Button variant="ghost" size="icon" className="rounded-sm text-muted-foreground hover:text-destructive"
                  onClick={(e) => handleDelete(ev.id, e)} data-testid={`delete-event-${ev.id}`}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
