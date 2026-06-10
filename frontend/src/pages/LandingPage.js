import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { toast } from 'sonner';
import api from '../lib/api';
import {
  Calculator, FileSpreadsheet, FileText, Users, Calendar, Copy, BarChart3,
  Check, ArrowRight, Zap, ShieldCheck, Clock, Layers,
} from 'lucide-react';

function FeatureCard({ icon: Icon, title, desc }) {
  return (
    <div className="border border-border p-6 bg-background hover:border-primary/50 transition-colors duration-200" data-testid={`feature-${title.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className="w-10 h-10 bg-primary/10 flex items-center justify-center mb-4">
        <Icon className="h-5 w-5 text-primary" />
      </div>
      <h3 className="font-heading font-bold text-base mb-1">{title}</h3>
      <p className="text-sm text-muted-foreground leading-relaxed">{desc}</p>
    </div>
  );
}

function PricingTier({ name, price, period, badge, features, highlight, testId }) {
  return (
    <div
      data-testid={testId}
      className={`p-6 transition-all duration-200 ${highlight ? 'bg-foreground text-background border-2 border-foreground' : 'border border-border bg-background'}`}
    >
      {badge && (
        <span className={`inline-block text-[10px] tracking-[0.2em] uppercase font-semibold px-2 py-0.5 mb-3 ${highlight ? 'bg-background text-foreground' : 'bg-primary text-primary-foreground'}`}>
          {badge}
        </span>
      )}
      <h3 className="font-heading text-xl font-bold mb-1">{name}</h3>
      <div className="flex items-baseline gap-1 mb-5">
        <span className="font-heading text-4xl font-black tracking-tight">{price}</span>
        {period && <span className={`text-xs ${highlight ? 'text-background/60' : 'text-muted-foreground'}`}>/{period}</span>}
      </div>
      <ul className="space-y-2.5 mb-6">
        {features.map((f, i) => (
          <li key={i} className="text-sm flex items-start gap-2">
            <Check className={`h-4 w-4 mt-0.5 flex-shrink-0 ${highlight ? 'text-background' : 'text-primary'}`} />
            <span className={highlight ? 'text-background' : ''}>{f}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FAQItem({ q, a }) {
  return (
    <div className="border-b border-border py-5">
      <p className="font-heading font-bold text-base mb-2">{q}</p>
      <p className="text-sm text-muted-foreground leading-relaxed">{a}</p>
    </div>
  );
}

export default function LandingPage() {
  const [form, setForm] = useState({ email: '', company: '', role: '', message: '' });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!form.email.trim()) return;
    setSubmitting(true);
    try {
      await api.post('/waitlist', form);
      setSubmitted(true);
      toast.success("You're on the list. We'll be in touch.");
    } catch (err) {
      // Surface as much detail as possible to help users (and us) diagnose
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      let msg;
      if (detail) {
        msg = detail;
      } else if (status === 429) {
        msg = 'Too many attempts. Please wait a minute and try again.';
      } else if (status === 400) {
        msg = 'Please check your email address.';
      } else if (!err?.response) {
        msg = 'Network error — could not reach the server. Check your connection and try again.';
      } else {
        msg = `Submission failed (HTTP ${status || '?'}). Please email us directly while we investigate.`;
      }
      console.error('Waitlist submit error:', { status, detail, err });
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const scrollToWaitlist = () => {
    document.getElementById('waitlist')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="landing-page">
      {/* Header */}
      <header className="border-b border-border sticky top-0 bg-background/95 backdrop-blur z-50">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="font-heading text-2xl font-black tracking-tight">MEBO</h1>
            <span className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">Payroll System</span>
          </div>
          <div className="flex items-center gap-2">
            <a href="#features" className="text-sm hover:text-primary transition-colors hidden sm:block px-3 py-1.5">Features</a>
            <a href="#pricing" className="text-sm hover:text-primary transition-colors hidden sm:block px-3 py-1.5">Pricing</a>
            <a href="#faq" className="text-sm hover:text-primary transition-colors hidden sm:block px-3 py-1.5">FAQ</a>
            <Link to="/login">
              <Button variant="ghost" size="sm" className="rounded-sm" data-testid="header-login-link">Login</Button>
            </Link>
            <Button onClick={scrollToWaitlist} size="sm" className="rounded-sm" data-testid="header-join-waitlist">
              Join Waitlist
            </Button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="border-b border-border">
        <div className="max-w-6xl mx-auto px-6 py-20 md:py-28 grid md:grid-cols-5 gap-10 items-center">
          <div className="md:col-span-3">
            <span className="inline-block text-[10px] tracking-[0.2em] uppercase font-semibold bg-primary/10 text-primary px-2 py-1 mb-5">
              Built for event production crews
            </span>
            <h2 className="font-heading text-4xl sm:text-5xl lg:text-6xl font-black tracking-tight leading-[1.05]">
              Event payroll without the spreadsheet pain.
            </h2>
            <p className="text-base text-muted-foreground mt-6 max-w-xl leading-relaxed">
              Track up to <strong className="text-foreground">200 crew per event</strong> across 10 days, with dual-rate handling, automatic gross / benefits / fund / deduction calculations, and branded PDF + Excel exports your accountant will actually accept.
            </p>
            <div className="flex flex-wrap gap-3 mt-7">
              <Button onClick={scrollToWaitlist} className="rounded-sm gap-2" size="lg" data-testid="hero-join-waitlist">
                Join the Waitlist <ArrowRight className="h-4 w-4" />
              </Button>
              <a href="#features">
                <Button variant="outline" className="rounded-sm" size="lg" data-testid="hero-see-features">See features</Button>
              </a>
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-2 mt-6 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" /> Setup in 5 minutes</span>
              <span className="flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5" /> No card required to join</span>
              <span className="flex items-center gap-1.5"><Zap className="h-3.5 w-3.5" /> Built by event veterans</span>
            </div>
          </div>
          <div className="md:col-span-2 border border-border bg-muted/30 p-6 font-mono text-xs">
            <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-3">Sum-Totals — Job #11211</p>
            <div className="space-y-1.5">
              <div className="flex justify-between border-b border-border/50 pb-1.5"><span>P. McDowell</span><span>$336.00</span></div>
              <div className="flex justify-between border-b border-border/50 pb-1.5"><span>J. Fletcher</span><span>$304.00</span></div>
              <div className="flex justify-between border-b border-border/50 pb-1.5"><span>S. Frost</span><span>$304.00</span></div>
              <div className="flex justify-between border-b border-border/50 pb-1.5"><span>I. Gallegos</span><span>$304.00</span></div>
              <div className="flex justify-between border-b border-border/50 pb-1.5"><span>T. Hawkins</span><span>$272.00</span></div>
              <div className="flex justify-between border-b border-border/50 pb-1.5"><span>L. Sutton</span><span>$256.00</span></div>
              <div className="flex justify-between border-b border-border/50 pb-1.5"><span>C. Dean</span><span>$400.00</span></div>
              <div className="flex justify-between border-b border-border/50 pb-1.5"><span>S. Meyer</span><span>$400.00</span></div>
              <div className="flex justify-between pt-2 font-bold"><span>GROSS</span><span>$2,576.00</span></div>
              <div className="flex justify-between text-muted-foreground"><span>+ Benefits (21%)</span><span>$540.96</span></div>
              <div className="flex justify-between text-muted-foreground"><span>+ Fund (2%)</span><span>$51.52</span></div>
              <div className="flex justify-between text-muted-foreground"><span>- Deductions (5%)</span><span>$128.80</span></div>
              <div className="flex justify-between font-heading text-sm font-black mt-3 pt-2 border-t border-foreground"><span>GRAND TOTAL</span><span>$3,040.32</span></div>
            </div>
          </div>
        </div>
      </section>

      {/* Pain points */}
      <section className="border-b border-border bg-muted/30">
        <div className="max-w-6xl mx-auto px-6 py-14">
          <p className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground mb-6 text-center">Stop fighting your tools</p>
          <div className="grid sm:grid-cols-3 gap-6 text-center max-w-4xl mx-auto">
            <div>
              <p className="font-heading text-3xl font-black tracking-tight">8 hrs</p>
              <p className="text-sm text-muted-foreground mt-1">average time production managers spend per week on broken payroll spreadsheets</p>
            </div>
            <div>
              <p className="font-heading text-3xl font-black tracking-tight">$300+/mo</p>
              <p className="text-sm text-muted-foreground mt-1">what legacy event-payroll software costs — built for enterprise, not your crew</p>
            </div>
            <div>
              <p className="font-heading text-3xl font-black tracking-tight">70%</p>
              <p className="text-sm text-muted-foreground mt-1">of small production companies still rely on fragile spreadsheets that break weekly</p>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="border-b border-border">
        <div className="max-w-6xl mx-auto px-6 py-20">
          <div className="max-w-2xl mb-12">
            <span className="text-[10px] tracking-[0.2em] uppercase font-semibold text-primary">Features</span>
            <h2 className="font-heading text-3xl sm:text-4xl font-black tracking-tight mt-2">Everything event payroll needs. Nothing it doesn&apos;t.</h2>
            <p className="text-sm text-muted-foreground mt-3">Designed by people who&apos;ve actually created payroll system from written or touring crews, festivals, and trade shows.</p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <FeatureCard icon={Layers} title="Event-based payroll" desc="Up to 10 work days per event, 200 employees, full ST/OT/DT breakdown for two rates plus a special rate column." />
            <FeatureCard icon={Calculator} title="Auto-calc gross & deductions" desc="Configurable Fund, Benefit, and Deduction percentages per event. Live calculation as you type — no formulas to maintain." />
            <FeatureCard icon={FileText} title="Branded PDF exports" desc="Summary, daily statements, and full-report PDFs with your company name, contact info, and a 5-column Grand Total footer." />
            <FeatureCard icon={FileSpreadsheet} title="Excel + CSV exports" desc="Full styled workbooks for your accountant. Plus per-employee running totals across all events." />
            <FeatureCard icon={Users} title="Roles & multi-user" desc="Admin, User, and Viewer roles. Crew leads enter hours, accountants view-only, you stay in control." />
            <FeatureCard icon={Copy} title="Clone past events" desc="Recurring weekly payroll? Clone last week's event in one click — employees and rates preserved, hours blanked." />
            <FeatureCard icon={Calendar} title="Pay period calendar" desc="Pick start/end dates once; Day 1–10 tabs auto-fill with the correct dates and labels." />
            <FeatureCard icon={BarChart3} title="Analytics dashboard" desc="Cross-event KPIs, monthly trend charts, per-employer breakdown. Employee running totals across all jobs." />
            <FeatureCard icon={ShieldCheck} title="Built to not break" desc="Validation prevents R1+R2 hour conflicts. Warnings catch missing rates. Per-row import errors keep your data clean." />
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="border-b border-border bg-muted/30">
        <div className="max-w-6xl mx-auto px-6 py-20">
          <div className="text-center mb-10">
            <span className="text-[10px] tracking-[0.2em] uppercase font-semibold text-primary">Pricing</span>
            <h2 className="font-heading text-3xl sm:text-4xl font-black tracking-tight mt-2">Simple. Honest. No surprises.</h2>
            <p className="text-sm text-muted-foreground mt-3">Final pricing TBD with our first 50 customers. Join the waitlist to lock in launch pricing.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-4 max-w-5xl mx-auto">
            <PricingTier
              testId="pricing-starter"
              name="Starter"
              price="$49"
              period="month"
              features={['1 user', 'Up to 50 employees / event', '5 events per month', 'PDF + Excel exports', 'Email support']}
            />
            <PricingTier
              testId="pricing-pro"
              name="Pro"
              price="$129"
              period="month"
              badge="Most popular"
              highlight
              features={['Up to 5 users', 'Unlimited employees', 'Unlimited events', 'All exports + analytics', 'Clone events, bulk import', 'Priority email support']}
            />
            <PricingTier
              testId="pricing-enterprise"
              name="Enterprise"
              price="Custom"
              features={['Unlimited users', 'White-label branding', 'Self-hosted option', 'Custom integrations', 'Phone support + SLA', 'Onboarding included']}
            />
          </div>
          <p className="text-xs text-muted-foreground text-center mt-8">14-day free trial · No credit card required · Cancel anytime</p>
        </div>
      </section>

      {/* Waitlist */}
      <section id="waitlist" className="border-b border-border">
        <div className="max-w-3xl mx-auto px-6 py-20">
          <div className="text-center mb-8">
            <span className="text-[10px] tracking-[0.2em] uppercase font-semibold text-primary">Early Access</span>
            <h2 className="font-heading text-3xl sm:text-4xl font-black tracking-tight mt-2">Be first in line.</h2>
            <p className="text-sm text-muted-foreground mt-3 max-w-xl mx-auto">
              We&apos;re onboarding our first 50 production companies. Join the waitlist and get founder pricing for life, a 30-min walkthrough with the team, and direct input on the roadmap.
            </p>
          </div>

          {submitted ? (
            <div className="border-2 border-primary p-8 text-center" data-testid="waitlist-success">
              <Check className="h-10 w-10 text-primary mx-auto mb-4" />
              <p className="font-heading text-xl font-bold mb-2">You&apos;re on the list.</p>
              <p className="text-sm text-muted-foreground">We&apos;ll reach out within 48 hours with a personal note and demo link.</p>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="border border-border p-6 sm:p-8 bg-background space-y-4" data-testid="waitlist-form">
              <div>
                <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Work email *</Label>
                <Input
                  type="email" required value={form.email} placeholder="you@company.com"
                  onChange={e => setForm(p => ({ ...p, email: e.target.value }))}
                  className="mt-1.5 rounded-sm h-10"
                  data-testid="waitlist-email-input"
                />
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Company</Label>
                  <Input
                    value={form.company} placeholder="Your production company"
                    onChange={e => setForm(p => ({ ...p, company: e.target.value }))}
                    className="mt-1.5 rounded-sm h-10"
                    data-testid="waitlist-company-input"
                  />
                </div>
                <div>
                  <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">Your role</Label>
                  <Input
                    value={form.role} placeholder="Production Manager"
                    onChange={e => setForm(p => ({ ...p, role: e.target.value }))}
                    className="mt-1.5 rounded-sm h-10"
                    data-testid="waitlist-role-input"
                  />
                </div>
              </div>
              <div>
                <Label className="text-xs tracking-[0.2em] uppercase font-semibold text-muted-foreground">What&apos;s your current payroll workflow? (optional)</Label>
                <textarea
                  value={form.message}
                  onChange={e => setForm(p => ({ ...p, message: e.target.value }))}
                  rows={3}
                  placeholder="We currently use Excel spreadsheets for crew payroll..."
                  className="mt-1.5 w-full rounded-sm border border-input bg-background p-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
                  data-testid="waitlist-message-input"
                />
              </div>
              <Button
                type="submit" disabled={submitting}
                className="w-full rounded-sm h-11 gap-2 mt-2"
                data-testid="waitlist-submit-button"
              >
                {submitting ? 'Joining...' : <>Join the Waitlist <ArrowRight className="h-4 w-4" /></>}
              </Button>
              <p className="text-[10px] text-muted-foreground text-center mt-2">We&apos;ll never share your email. One follow-up message, then nothing until launch.</p>
            </form>
          )}
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="border-b border-border">
        <div className="max-w-3xl mx-auto px-6 py-20">
          <div className="text-center mb-10">
            <span className="text-[10px] tracking-[0.2em] uppercase font-semibold text-primary">FAQ</span>
            <h2 className="font-heading text-3xl sm:text-4xl font-black tracking-tight mt-2">Common questions</h2>
          </div>
          <div>
            <FAQItem
              q="Who is MEBO Payroll for?"
              a="Event production companies, IATSE shops, stagehand agencies, AV rental houses, touring production managers, theatre companies, trade show contractors — anyone who runs payroll by job/event instead of by salary."
            />
            <FAQItem
              q="Does it replace ADP or Gusto?"
              a="Not yet. MEBO calculates gross pay, benefits, fund contributions, and deductions per event, then exports the data your existing payroll provider needs. Think of it as the smart spreadsheet that finally works — and feeds clean numbers to whoever cuts the checks."
            />
            <FAQItem
              q="How does the dual-rate system work?"
              a="Each employee can have a Rate 1 (e.g., load-in rate) and a Rate 2 (e.g., show rate), plus an optional Special Rate. On any given day, an employee uses either Rate 1 OR Rate 2 hours, never both — we enforce that with validation. ST/OT/DT multipliers apply automatically."
            />
            <FAQItem
              q="Can I export to my own accounting software?"
              a="Yes. Every event exports to native Excel (.xlsx) with full styling, plus PDF for printable/emailable summaries. You can also download per-employee running totals across all events for year-end reporting."
            />
            <FAQItem
              q="Is there a self-hosted option?"
              a="Yes — Enterprise tier customers can host MEBO on their own infrastructure with a perpetual license. Contact us during waitlist for details."
            />
            <FAQItem
              q="When does the public beta open?"
              a="We're onboarding waitlist members in batches starting soon. Founder pricing locks in for life if you join during the waitlist phase."
            />
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border">
        <div className="max-w-6xl mx-auto px-6 py-10 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <h3 className="font-heading text-xl font-black tracking-tight">MEBO</h3>
            <span className="text-[10px] tracking-[0.2em] uppercase font-semibold text-muted-foreground">Payroll System</span>
          </div>
          <p className="text-xs text-muted-foreground">© {new Date().getFullYear()} MEBO Payroll. Built for crews, by crews.</p>
          <div className="flex items-center gap-3">
            <Link to="/login" className="text-xs hover:text-primary transition-colors">Login</Link>
            <a href="#waitlist" className="text-xs hover:text-primary transition-colors">Waitlist</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
