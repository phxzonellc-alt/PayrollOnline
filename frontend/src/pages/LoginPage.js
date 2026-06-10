import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
      navigate('/app');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Invalid credentials');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <div className="w-full max-w-sm border border-border p-8">
        <div className="mb-8">
          <h1 className="font-heading text-4xl font-black tracking-tight text-foreground">MEBO</h1>
          <p className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground mt-2">
            Payroll System
          </p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="email" className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">
              Email
            </Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="admin@example.com"
              data-testid="login-email-input"
              className="mt-1 rounded-sm"
              required
            />
          </div>
          <div>
            <Label htmlFor="password" className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">
              Password
            </Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Enter password"
              data-testid="login-password-input"
              className="mt-1 rounded-sm"
              required
            />
          </div>
          {error && <p className="text-sm text-destructive" data-testid="login-error">{error}</p>}
          <Button
            type="submit"
            disabled={loading}
            data-testid="login-submit-button"
            className="w-full rounded-sm font-semibold"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </Button>
        </form>
      </div>
    </div>
  );
}
