import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  alpha,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  FormControlLabel,
  Grid,
  LinearProgress,
  MenuItem,
  Paper,
  Snackbar,
  Stack,
  Switch,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from '@mui/material'
import { ThemeProvider, useTheme } from '@mui/material/styles'
import {
  OpenInNew as OpenIcon,
  ContentCopy as CopyIcon,
  Upload as UploadIcon,
  Campaign as AdIcon,
  Palette as PaletteIcon,
} from '@mui/icons-material'
import {
  BrandingEdit,
  formatNaira,
  sponsorAPI,
  SponsorBranding,
  SponsorDashboard,
  SponsorLearner,
  SponsorStatement,
  SPONSOR_TOKEN_KEY,
} from '../services/api'
import { CertificateActions } from '../components/AdminKit'
import { BrandMark, brandTheme, DEFAULT_BRAND, SponsorAdvertCard } from '../components/SponsorBrand'

/**
 * Sponsor portal — what a church, company or state sees: how many of its
 * people enrolled and certified, its codes and join links, the monthly
 * statement and a pay button. Names and progress only; never phone numbers.
 *
 * White-labelled: it wears the sponsor's colour and logo, and is where the
 * sponsor designs its landing page (/s/<code>) and the advert its learners see.
 */

const errorText = (e: unknown, fallback: string): string => {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg).replace(/^Value error, /, '')
  return typeof detail === 'string' ? detail : fallback
}

const card = { p: { xs: 2, md: 3 }, border: '1px solid', borderColor: 'grey.200', borderRadius: 3, bgcolor: 'white' } as const

const Stat: React.FC<{ label: string; value: React.ReactNode; hint?: string }> = ({ label, value, hint }) => (
  <Paper elevation={0} sx={{ ...card, height: '100%' }}>
    <Typography variant="body2" color="text.secondary">{label}</Typography>
    <Typography variant="h4" fontWeight={800} sx={{ mt: 0.5, color: 'primary.main' }}>{value}</Typography>
    {hint && <Typography variant="caption" color="text.secondary">{hint}</Typography>}
  </Paper>
)

const LoginPanel: React.FC<{ onDone: () => void }> = ({ onDone }) => {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const r = await sponsorAPI.login(email, password)
      localStorage.setItem(SPONSOR_TOKEN_KEY, r.access_token)
      onDone()
    } catch (err) {
      setError(errorText(err, 'Sign-in failed.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', bgcolor: '#F4F5F2', px: 2 }}>
      <Paper elevation={0} sx={{ ...card, p: { xs: 3, md: 4 }, width: '100%', maxWidth: 420 }}>
        <Typography variant="overline" color="text.secondary">Sponsor dashboard</Typography>
        <Typography variant="h5" fontWeight={800}>Sign in</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Use the email and password set up for your organisation.
        </Typography>
        <Box component="form" onSubmit={submit}>
          <Stack spacing={2}>
            <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required fullWidth />
            <TextField label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required fullWidth />
            {error && <Alert severity="error">{error}</Alert>}
            <Button type="submit" variant="contained" size="large" disabled={busy} sx={{ fontWeight: 700 }}>
              {busy ? <CircularProgress size={22} color="inherit" /> : 'Sign in'}
            </Button>
          </Stack>
        </Box>
      </Paper>
    </Box>
  )
}

const recentMonths = (n: number) => {
  const out: { year: number; month: number; label: string }[] = []
  const d = new Date()
  for (let i = 0; i < n; i++) {
    const m = new Date(d.getFullYear(), d.getMonth() - i, 1)
    out.push({ year: m.getFullYear(), month: m.getMonth() + 1, label: m.toLocaleString('en-NG', { month: 'long', year: 'numeric' }) })
  }
  return out
}

const landingUrl = (code: string) => `${window.location.origin}/s/${encodeURIComponent(code)}`

// ---------------------------------------------------------------------------
// branding + advert editor
// ---------------------------------------------------------------------------

const SWATCHES = ['#008751', '#0B5FFF', '#6A1B9A', '#C62828', '#EF6C00', '#00838F', '#263238', '#AD1457']

const editable = (b: SponsorBranding): Required<BrandingEdit> => ({
  brand_color: b.brand_color, tagline: b.tagline, welcome_message: b.welcome_message, website_url: b.website_url,
  ad_enabled: b.ad_enabled, ad_headline: b.ad_headline, ad_body: b.ad_body, ad_cta_label: b.ad_cta_label, ad_cta_url: b.ad_cta_url,
})

const ImagePicker: React.FC<{ label: string; hint: string; onPick: (f: File) => void; busy: boolean }> = ({ label, hint, onPick, busy }) => {
  const input = useRef<HTMLInputElement>(null)
  return (
    <>
      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg"
        hidden
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onPick(f); e.target.value = '' }}
      />
      <Button variant="outlined" size="small" startIcon={busy ? <CircularProgress size={14} /> : <UploadIcon />} disabled={busy}
        onClick={() => input.current?.click()}>
        {label}
      </Button>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>{hint}</Typography>
    </>
  )
}

const BrandingEditor: React.FC<{
  orgName: string
  branding: SponsorBranding
  previewCode: string | null
  onSaved: (b: SponsorBranding) => void
  onPreviewColor: (c: string | null) => void
}> = ({ orgName, branding, previewCode, onSaved, onPreviewColor }) => {
  const base = useTheme()
  const [form, setForm] = useState(() => editable(branding))
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState<'logo' | 'ad_image' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const dirty = JSON.stringify(form) !== JSON.stringify(editable(branding))
  const set = <K extends keyof BrandingEdit>(key: K, value: BrandingEdit[K]) => setForm((f) => ({ ...f, [key]: value }))
  const text = (key: keyof BrandingEdit) => ({
    value: (form[key] as string | null) ?? '',
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => set(key, e.target.value as never),
  })

  useEffect(() => { onPreviewColor(form.brand_color) }, [form.brand_color, onPreviewColor])

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const b = await sponsorAPI.updateBranding({
        ...form,
        brand_color: form.brand_color || '',
        tagline: form.tagline ?? '', welcome_message: form.welcome_message ?? '', website_url: form.website_url ?? '',
        ad_headline: form.ad_headline ?? '', ad_body: form.ad_body ?? '', ad_cta_label: form.ad_cta_label ?? '', ad_cta_url: form.ad_cta_url ?? '',
      })
      onSaved(b)
      setForm(editable(b))
      setSaved(true)
    } catch (e) {
      setError(errorText(e, 'Could not save your changes.'))
    } finally {
      setSaving(false)
    }
  }

  const upload = async (kind: 'logo' | 'ad_image', file: File) => {
    setUploading(kind)
    setError(null)
    try {
      onSaved(await sponsorAPI.uploadBrandImage(kind, file))
    } catch (e) {
      setError(errorText(e, 'Could not upload that image.'))
    } finally {
      setUploading(null)
    }
  }

  const removeImage = async () => {
    try {
      onSaved(await sponsorAPI.removeAdImage())
    } catch (e) {
      setError(errorText(e, 'Could not remove the image.'))
    }
  }

  const previewTheme = useMemo(() => brandTheme(base, form.brand_color), [base, form.brand_color])
  const color = form.brand_color || DEFAULT_BRAND
  const advertPreview = form.ad_headline
    ? {
        headline: form.ad_headline, body: form.ad_body, cta_label: form.ad_cta_label,
        cta_url: form.ad_cta_url || null, image_url: branding.ad_image_url,
      }
    : null

  return (
    <Grid container spacing={3}>
      <Grid item xs={12} lg={6}>
        <Stack spacing={3}>
          {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}

          <Paper elevation={0} sx={card}>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
              <PaletteIcon color="primary" />
              <Typography fontWeight={800} sx={{ fontSize: '1.1rem' }}>Your page</Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
              Your learners land on a page with your name, logo and colour. Your logo is also printed on their certificates.
            </Typography>

            <Stack spacing={2.5}>
              <Stack direction="row" spacing={2} alignItems="center">
                <BrandMark name={orgName} logoUrl={branding.logo_url} size={56} />
                <Box>
                  <ImagePicker label={branding.logo_url ? 'Replace logo' : 'Upload logo'} hint="PNG or JPEG, up to 1 MB. A transparent PNG looks best."
                    busy={uploading === 'logo'} onPick={(f) => upload('logo', f)} />
                </Box>
              </Stack>

              <Box>
                <Typography variant="body2" fontWeight={700} sx={{ mb: 1 }}>Brand colour</Typography>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                  {SWATCHES.map((s) => (
                    <Box
                      key={s}
                      component="button"
                      type="button"
                      aria-label={`Use ${s}`}
                      onClick={() => set('brand_color', s)}
                      sx={{
                        width: 32, height: 32, borderRadius: '50%', bgcolor: s, cursor: 'pointer', border: '3px solid',
                        borderColor: color.toUpperCase() === s ? 'grey.900' : 'white', boxShadow: '0 0 0 1px rgba(0,0,0,0.12)',
                      }}
                    />
                  ))}
                  <Box component="input" type="color" value={color} onChange={(e: React.ChangeEvent<HTMLInputElement>) => set('brand_color', e.target.value.toUpperCase())}
                    aria-label="Custom colour" sx={{ width: 40, height: 34, border: 'none', bgcolor: 'transparent', cursor: 'pointer', p: 0 }} />
                  <TextField size="small" value={form.brand_color ?? ''} placeholder={DEFAULT_BRAND}
                    onChange={(e) => set('brand_color', e.target.value)} sx={{ width: 120 }} inputProps={{ maxLength: 7 }} />
                </Stack>
              </Box>

              <TextField label="Tagline" placeholder="Raising a digital generation" {...text('tagline')}
                inputProps={{ maxLength: 160 }} helperText="One line under the headline on your page." fullWidth />
              <TextField label="Welcome message" multiline minRows={3} {...text('welcome_message')}
                inputProps={{ maxLength: 1000 }} helperText={`A note to your people. ${(form.welcome_message ?? '').length}/1000`} fullWidth />
              <TextField label="Your website" placeholder="https://" {...text('website_url')} inputProps={{ maxLength: 500 }} fullWidth />
            </Stack>
          </Paper>

          <Paper elevation={0} sx={card}>
            <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <AdIcon color="primary" />
                <Typography fontWeight={800} sx={{ fontSize: '1.1rem' }}>Your advert</Typography>
              </Stack>
              <FormControlLabel
                control={<Switch checked={!!form.ad_enabled} onChange={(e) => set('ad_enabled', e.target.checked)} />}
                label={form.ad_enabled ? 'Showing' : 'Off'}
                labelPlacement="start"
              />
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
              Promote an event, product, service or opportunity. It appears on your page and inside the course for your learners,
              labelled "Sponsored".
            </Typography>
            {branding.ad_suspended && (
              <Alert severity="warning" sx={{ mb: 2 }}>
                MNAIR has paused your advert. Contact us to get it running again.
              </Alert>
            )}
            <Stack spacing={2.5}>
              <TextField label="Headline" placeholder="Join our Sunday Tech Service" {...text('ad_headline')}
                inputProps={{ maxLength: 120 }} helperText={`Required for the advert to show. ${(form.ad_headline ?? '').length}/120`} fullWidth />
              <TextField label="Message" multiline minRows={3} {...text('ad_body')}
                inputProps={{ maxLength: 600 }} helperText={`${(form.ad_body ?? '').length}/600`} fullWidth />
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField label="Button text" placeholder="Learn more" {...text('ad_cta_label')} inputProps={{ maxLength: 40 }} sx={{ flex: 1 }} />
                <TextField label="Button link" placeholder="https://" {...text('ad_cta_url')} inputProps={{ maxLength: 500 }} sx={{ flex: 2 }} />
              </Stack>
              <Box>
                <Stack direction="row" spacing={1} alignItems="center">
                  <ImagePicker label={branding.ad_image_url ? 'Replace image' : 'Add an image'} hint="PNG or JPEG, up to 2 MB. Landscape works best."
                    busy={uploading === 'ad_image'} onPick={(f) => upload('ad_image', f)} />
                </Stack>
                {branding.ad_image_url && <Button size="small" color="inherit" onClick={removeImage} sx={{ mt: 0.5 }}>Remove image</Button>}
              </Box>
            </Stack>
          </Paper>

          <Stack direction="row" spacing={1.5} alignItems="center"
            sx={{ position: 'sticky', bottom: 12, zIndex: 2, p: 1.5, borderRadius: 3, bgcolor: alpha('#FFFFFF', 0.95), border: '1px solid', borderColor: 'grey.200', boxShadow: dirty ? 3 : 0 }}>
            <Button variant="contained" size="large" onClick={save} disabled={!dirty || saving} sx={{ fontWeight: 700, px: 4 }}>
              {saving ? <CircularProgress size={22} color="inherit" /> : 'Save changes'}
            </Button>
            {dirty && <Button onClick={() => setForm(editable(branding))}>Discard</Button>}
            <Box sx={{ flex: 1 }} />
            {previewCode && (
              <Button href={landingUrl(previewCode)} target="_blank" rel="noopener noreferrer" endIcon={<OpenIcon fontSize="small" />}>
                Open my page
              </Button>
            )}
          </Stack>
        </Stack>
      </Grid>

      <Grid item xs={12} lg={6}>
        <Box sx={{ position: { lg: 'sticky' }, top: 16 }}>
          <Typography variant="overline" color="text.secondary">Live preview</Typography>
          <ThemeProvider theme={previewTheme}>
            <Paper elevation={0} sx={{ ...card, p: 0, overflow: 'hidden' }}>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ px: 2, py: 1.25, borderBottom: '1px solid', borderColor: 'grey.200' }}>
                <BrandMark name={orgName} logoUrl={branding.logo_url} size={28} />
                <Typography fontWeight={800} noWrap sx={{ flex: 1, fontSize: '0.9rem' }}>{orgName}</Typography>
                <Chip size="small" color="primary" label="Start" />
              </Stack>
              <Box sx={{ background: (t) => `linear-gradient(135deg, ${t.palette.primary.dark}, ${t.palette.primary.main})`, color: 'primary.contrastText', p: 3 }}>
                <Typography variant="caption" sx={{ opacity: 0.85, fontWeight: 700 }}>Free for you · Sponsored by {orgName}</Typography>
                <Typography sx={{ fontWeight: 900, fontSize: '1.7rem', lineHeight: 1.1, mt: 1 }}>Learn AI in 7 days. On us.</Typography>
                <Typography sx={{ mt: 1, opacity: 0.92, fontSize: '0.95rem' }}>
                  {form.tagline || `${orgName} is covering your course and certificate.`}
                </Typography>
                {form.welcome_message && (
                  <Paper elevation={0} sx={{ mt: 2, p: 1.5, borderRadius: 2, fontSize: '0.85rem', whiteSpace: 'pre-line' }}>
                    {form.welcome_message}
                  </Paper>
                )}
              </Box>
              <Box sx={{ p: 2, bgcolor: '#FAFAF7' }}>
                {advertPreview ? (
                  <Box sx={{ opacity: form.ad_enabled && !branding.ad_suspended ? 1 : 0.45 }}>
                    <SponsorAdvertCard advert={advertPreview} sponsorName={orgName} />
                    {(!form.ad_enabled || branding.ad_suspended) && (
                      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                        Not showing to learners {branding.ad_suspended ? '(paused by MNAIR)' : '(switch it on above)'}.
                      </Typography>
                    )}
                  </Box>
                ) : (
                  <Box sx={{ border: '2px dashed', borderColor: 'grey.300', borderRadius: 3, p: 3, textAlign: 'center', color: 'text.secondary' }}>
                    <AdIcon sx={{ fontSize: 32, opacity: 0.5 }} />
                    <Typography variant="body2">Your advert will appear here. Add a headline to get started.</Typography>
                  </Box>
                )}
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 2, mb: 1 }}>
                  Inside the course, learners see:
                </Typography>
                {advertPreview && <SponsorAdvertCard advert={advertPreview} sponsorName={orgName} variant="compact" />}
              </Box>
            </Paper>
          </ThemeProvider>
        </Box>
      </Grid>

      <Snackbar open={saved} autoHideDuration={2500} onClose={() => setSaved(false)} message="Saved. Your page is updated." />
    </Grid>
  )
}

// ---------------------------------------------------------------------------
// page
// ---------------------------------------------------------------------------

type PortalTab = 'overview' | 'brand' | 'learners' | 'billing'

const SponsorPortal: React.FC = () => {
  const base = useTheme()
  const [authed, setAuthed] = useState(() => !!localStorage.getItem(SPONSOR_TOKEN_KEY))
  const [dash, setDash] = useState<SponsorDashboard | null>(null)
  const [tab, setTab] = useState<PortalTab>('overview')
  const [previewColor, setPreviewColor] = useState<string | null | undefined>(undefined)
  const [learners, setLearners] = useState<SponsorLearner[]>([])
  const [learnerTotal, setLearnerTotal] = useState(0)
  const [page, setPage] = useState(0)
  const months = recentMonths(12)
  const [period, setPeriod] = useState(`${months[0].year}-${months[0].month}`)
  const [statement, setStatement] = useState<SponsorStatement | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [paying, setPaying] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)
  const PAGE = 50

  const handleAuthError = useCallback((e: unknown) => {
    const status = (e as { response?: { status?: number } })?.response?.status
    if (status === 401 || status === 403) {
      localStorage.removeItem(SPONSOR_TOKEN_KEY)
      setAuthed(false)
      return true
    }
    return false
  }, [])

  const load = useCallback(async () => {
    try {
      setDash(await sponsorAPI.dashboard())
    } catch (e) {
      if (!handleAuthError(e)) setError(errorText(e, 'Could not load your dashboard.'))
    }
  }, [handleAuthError])

  useEffect(() => { if (authed) load() }, [authed, load])

  useEffect(() => {
    if (!authed) return
    sponsorAPI.learners(page * PAGE, PAGE)
      .then((r) => { setLearners(r.items); setLearnerTotal(r.total) })
      .catch((e) => { if (!handleAuthError(e)) setError(errorText(e, 'Could not load learners.')) })
  }, [authed, page, handleAuthError])

  useEffect(() => {
    if (!authed) return
    const [y, m] = period.split('-').map(Number)
    sponsorAPI.statement(y, m).then(setStatement).catch((e) => { if (!handleAuthError(e)) setStatement(null) })
  }, [authed, period, handleAuthError])

  useEffect(() => {
    if (dash) document.title = `${dash.organization.name} · Sponsor dashboard`
  }, [dash])

  // While editing, the whole portal previews the colour being picked
  const activeColor = tab === 'brand' && previewColor !== undefined ? previewColor : dash?.branding.brand_color
  const theme = useMemo(() => brandTheme(base, activeColor), [base, activeColor])
  const onPreviewColor = useCallback((c: string | null) => setPreviewColor(c), [])

  const pay = async (purpose: 'deposit' | 'balance') => {
    setPaying(true)
    setError(null)
    try {
      const r = await sponsorAPI.pay(purpose)
      window.location.href = r.authorization_url
    } catch (e) {
      setError(errorText(e, 'Could not start the payment.'))
      setPaying(false)
    }
  }

  const downloadCsv = async () => {
    try {
      const blob = await sponsorAPI.learnersCsv()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'mnair-learners.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(errorText(e, 'Could not download the list.'))
    }
  }

  const copy = (value: string, what: string) => {
    navigator.clipboard?.writeText(value)
    setCopied(what)
  }

  const signOut = () => {
    localStorage.removeItem(SPONSOR_TOKEN_KEY)
    setDash(null)
    setAuthed(false)
  }

  if (!authed) return <LoginPanel onDone={() => setAuthed(true)} />
  if (!dash) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 10 }}>
        {error ? <Alert severity="error">{error}</Alert> : <CircularProgress />}
      </Box>
    )
  }

  const { organization: org, learners: l, account, branding } = dash
  const maxDay = Math.max(1, ...Object.values(l.days_completed))
  const mainCode = dash.codes.find((c) => c.is_active)?.code ?? null

  return (
    <ThemeProvider theme={theme}>
      <Box sx={{ minHeight: '100vh', bgcolor: '#F4F5F2' }}>
        {/* branded header */}
        <Box sx={{ background: (t) => `linear-gradient(135deg, ${t.palette.primary.dark}, ${t.palette.primary.main})`, color: 'primary.contrastText' }}>
          <Container maxWidth="lg" sx={{ pt: { xs: 2.5, md: 3.5 } }}>
            <Stack direction="row" alignItems="center" spacing={2} flexWrap="wrap" useFlexGap>
              <BrandMark name={org.name} logoUrl={branding.logo_url} size={52} light />
              <Box sx={{ flex: 1, minWidth: 200 }}>
                <Typography variant="overline" sx={{ opacity: 0.8, lineHeight: 1.5 }}>Sponsor dashboard</Typography>
                <Typography variant="h4" fontWeight={900} sx={{ lineHeight: 1.1, fontSize: { xs: '1.6rem', md: '2.1rem' } }}>{org.name}</Typography>
                <Typography sx={{ opacity: 0.85, fontSize: '0.9rem', mt: 0.5 }}>
                  {org.package.charAt(0).toUpperCase() + org.package.slice(1)} package · {formatNaira(org.price_per_certificate_kobo)} per certified learner
                  {org.learner_cap ? ` · up to ${org.learner_cap.toLocaleString()} learners` : ''}
                </Typography>
              </Box>
              <Stack direction="row" spacing={1}>
                {mainCode && (
                  <Button href={landingUrl(mainCode)} target="_blank" rel="noopener noreferrer" variant="contained" endIcon={<OpenIcon fontSize="small" />}
                    sx={{ bgcolor: 'primary.contrastText', color: 'primary.main', fontWeight: 700, boxShadow: 'none', '&:hover': { bgcolor: (t) => alpha(t.palette.primary.contrastText, 0.9) } }}>
                    View my page
                  </Button>
                )}
                <Button onClick={signOut} sx={{ color: 'primary.contrastText' }}>Sign out</Button>
              </Stack>
            </Stack>
            <Tabs
              value={tab}
              onChange={(_, v) => setTab(v)}
              variant="scrollable"
              allowScrollButtonsMobile
              textColor="inherit"
              TabIndicatorProps={{ sx: { bgcolor: 'primary.contrastText', height: 3 } }}
              sx={{ mt: 2.5, '& .MuiTab-root': { fontWeight: 700, opacity: 0.8, '&.Mui-selected': { opacity: 1 } } }}
            >
              <Tab value="overview" label="Overview" />
              <Tab value="brand" label="Your page & advert" />
              <Tab value="learners" label={`Learners (${learnerTotal.toLocaleString()})`} />
              <Tab value="billing" label="Billing" />
            </Tabs>
          </Container>
        </Box>

        <Container maxWidth="lg" sx={{ py: { xs: 3, md: 4 } }}>
          {error && <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>{error}</Alert>}

          {tab === 'overview' && (
            <>
              {!branding.ad_live && !branding.ad_suspended && (
                <Paper elevation={0} sx={{ ...card, mb: 3, display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap',
                  bgcolor: (t) => alpha(t.palette.primary.main, 0.06), borderColor: (t) => alpha(t.palette.primary.main, 0.25) }}>
                  <AdIcon color="primary" sx={{ fontSize: 36 }} />
                  <Box sx={{ flex: 1, minWidth: 220 }}>
                    <Typography fontWeight={800}>Reach your learners with an advert</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {l.enrolled.toLocaleString()} people see your page and course. Promote an event, product or opportunity to them.
                    </Typography>
                  </Box>
                  <Button variant="contained" onClick={() => setTab('brand')} sx={{ fontWeight: 700, boxShadow: 'none' }}>Create advert</Button>
                </Paper>
              )}

              <Grid container spacing={2} sx={{ mb: 3 }}>
                <Grid item xs={6} md={3}><Stat label="Enrolled" value={l.enrolled.toLocaleString()} /></Grid>
                <Grid item xs={6} md={3}><Stat label="Active this week" value={l.active_last_7_days.toLocaleString()} /></Grid>
                <Grid item xs={6} md={3}><Stat label="Certified" value={l.certified.toLocaleString()} hint={`${l.completion_rate}% of enrolled`} /></Grid>
                <Grid item xs={6} md={3}>
                  <Stat label="Average quiz score" value={l.average_quiz_score != null ? `${l.average_quiz_score}%` : '–'} />
                </Grid>
              </Grid>

              <Grid container spacing={2} sx={{ mb: 3 }}>
                <Grid item xs={12} md={6}>
                  <Paper elevation={0} sx={{ ...card, height: '100%' }}>
                    <Typography fontWeight={800} sx={{ mb: 2 }}>Where your learners are</Typography>
                    {Array.from({ length: 8 }, (_, d) => (
                      <Stack key={d} direction="row" alignItems="center" spacing={1.5} sx={{ mb: 0.9 }}>
                        <Typography variant="body2" sx={{ width: 110 }}>{d === 0 ? 'Not started' : d === 7 ? 'Finished' : `Done day ${d}`}</Typography>
                        <LinearProgress
                          variant="determinate"
                          value={(100 * (l.days_completed[String(d)] || 0)) / maxDay}
                          sx={{ flex: 1, height: 10, borderRadius: 5, bgcolor: (t) => alpha(t.palette.primary.main, 0.1) }}
                        />
                        <Typography variant="body2" sx={{ width: 48, textAlign: 'right' }}>{l.days_completed[String(d)] || 0}</Typography>
                      </Stack>
                    ))}
                  </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Paper elevation={0} sx={{ ...card, height: '100%' }}>
                    <Typography fontWeight={800} sx={{ mb: 0.5 }}>Your codes and links</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      Share your page link. It shows your branding and fills in the code for your people.
                    </Typography>
                    <Stack spacing={1.5}>
                      {dash.codes.map((c) => (
                        <Box key={c.code} sx={{ p: 1.5, borderRadius: 2, border: '1px solid', borderColor: 'grey.200' }}>
                          <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
                            <Typography sx={{ fontFamily: 'monospace', fontWeight: 800, letterSpacing: 1 }}>{c.code}</Typography>
                            {c.label && <Typography variant="body2" color="text.secondary">{c.label}</Typography>}
                            {!c.is_active && <Chip size="small" label="inactive" />}
                            <Box sx={{ flex: 1 }} />
                            <Typography variant="body2" color="text.secondary">
                              {c.enrolled}{c.max_enrolments ? ` / ${c.max_enrolments}` : ''} enrolled
                            </Typography>
                          </Stack>
                          {c.is_active && (
                            <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
                              <Button size="small" variant="contained" startIcon={<CopyIcon fontSize="small" />} sx={{ boxShadow: 'none' }}
                                onClick={() => copy(landingUrl(c.code), 'Page link')}>Page link</Button>
                              <Button size="small" startIcon={<CopyIcon fontSize="small" />} onClick={() => copy(c.join_url, 'Direct join link')}>Direct link</Button>
                              {c.telegram_url && (
                                <Button size="small" startIcon={<CopyIcon fontSize="small" />} onClick={() => copy(c.telegram_url!, 'Telegram link')}>Telegram</Button>
                              )}
                            </Stack>
                          )}
                        </Box>
                      ))}
                    </Stack>
                  </Paper>
                </Grid>
              </Grid>
            </>
          )}

          {tab === 'brand' && (
            <BrandingEditor
              orgName={org.name}
              branding={branding}
              previewCode={mainCode}
              onPreviewColor={onPreviewColor}
              onSaved={(b) => setDash((d) => (d ? { ...d, branding: b } : d))}
            />
          )}

          {tab === 'learners' && (
            <Paper elevation={0} sx={card}>
              <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
                <Typography fontWeight={800}>Learners ({learnerTotal.toLocaleString()})</Typography>
                <Button size="small" variant="outlined" onClick={downloadCsv}>Download CSV</Button>
              </Stack>
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Name</TableCell><TableCell>Language</TableCell><TableCell align="right">Days done</TableCell>
                      <TableCell>Certificate</TableCell><TableCell>Joined</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {learners.map((x, i) => (
                      <TableRow key={i}>
                        <TableCell>{x.name}</TableCell>
                        <TableCell>{x.language.toUpperCase()}</TableCell>
                        <TableCell align="right">{x.completed_days}/7</TableCell>
                        <TableCell>
                          {x.certified && x.certificate_id ? (
                            <Stack direction="row" alignItems="center" spacing={0.5}>
                              <Chip size="small" color="success" label={x.certificate_id} />
                              <CertificateActions compact certificateId={x.certificate_id}
                                fetchPdf={sponsorAPI.certificatePdf} makeLink={(cid, days) => sponsorAPI.certificateLink(cid, days)} />
                            </Stack>
                          ) : '–'}
                        </TableCell>
                        <TableCell>{x.joined_at ? new Date(x.joined_at).toLocaleDateString('en-NG') : '–'}</TableCell>
                      </TableRow>
                    ))}
                    {learners.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={5} sx={{ textAlign: 'center', color: 'text.secondary', py: 4 }}>
                          No learners yet. Share your page link to get started.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </Box>
              {learnerTotal > PAGE && (
                <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ mt: 1.5 }}>
                  <Button size="small" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
                  <Button size="small" disabled={(page + 1) * PAGE >= learnerTotal} onClick={() => setPage(page + 1)}>Next</Button>
                </Stack>
              )}
            </Paper>
          )}

          {tab === 'billing' && (
            <Grid container spacing={2}>
              <Grid item xs={12} md={5}>
                <Paper elevation={0} sx={{ ...card, height: '100%' }}>
                  <Typography fontWeight={800} sx={{ mb: 1.5 }}>Account</Typography>
                  <Table size="small">
                    <TableBody>
                      <TableRow><TableCell>Certificates billed</TableCell><TableCell align="right">{account.certificates_billed.toLocaleString()}</TableCell></TableRow>
                      <TableRow><TableCell>Total charged</TableCell><TableCell align="right">{formatNaira(account.charged_kobo)}</TableCell></TableRow>
                      <TableRow><TableCell>Total paid</TableCell><TableCell align="right">{formatNaira(account.paid_kobo)}</TableCell></TableRow>
                      <TableRow><TableCell>Deposit credit left</TableCell><TableCell align="right">{formatNaira(account.credit_remaining_kobo)}</TableCell></TableRow>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 700 }}>Amount due</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{formatNaira(account.amount_due_kobo)}</TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                  <Stack direction="row" spacing={1} sx={{ mt: 2 }} flexWrap="wrap" gap={1}>
                    {account.deposit_outstanding_kobo > 0 && (
                      <Button variant="contained" disabled={paying || !dash.payments_enabled} onClick={() => pay('deposit')}>
                        Pay deposit {formatNaira(account.deposit_outstanding_kobo)}
                      </Button>
                    )}
                    {account.amount_due_kobo > 0 && (
                      <Button variant="contained" color="success" disabled={paying || !dash.payments_enabled} onClick={() => pay('balance')}>
                        Pay {formatNaira(account.amount_due_kobo)}
                      </Button>
                    )}
                  </Stack>
                  {!dash.payments_enabled && (
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                      Online payment is not switched on yet. Contact MNAIR for bank transfer details.
                    </Typography>
                  )}
                </Paper>
              </Grid>
              <Grid item xs={12} md={7}>
                <Paper elevation={0} sx={{ ...card, height: '100%' }}>
                  <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }} flexWrap="wrap" gap={1}>
                    <Typography fontWeight={800}>Monthly statement</Typography>
                    <TextField select size="small" value={period} onChange={(e) => setPeriod(e.target.value)}>
                      {months.map((m) => <MenuItem key={`${m.year}-${m.month}`} value={`${m.year}-${m.month}`}>{m.label}</MenuItem>)}
                    </TextField>
                  </Stack>
                  {statement && (
                    <Table size="small">
                      <TableBody>
                        <TableRow>
                          <TableCell>Opening balance</TableCell>
                          <TableCell align="right">{formatNaira(statement.opening_balance_kobo)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Certificates issued ({statement.certificates_issued} × {formatNaira(statement.price_per_certificate_kobo)})</TableCell>
                          <TableCell align="right">{formatNaira(statement.charges_kobo)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Payments received</TableCell>
                          <TableCell align="right">−{formatNaira(statement.payments_kobo)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 700 }}>
                            {statement.closing_balance_kobo < 0 ? 'Closing credit' : 'Closing balance'}
                          </TableCell>
                          <TableCell align="right" sx={{ fontWeight: 700 }}>{formatNaira(Math.abs(statement.closing_balance_kobo))}</TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  )}
                </Paper>
              </Grid>
            </Grid>
          )}

          <Typography variant="caption" color="text.secondary" display="block" align="center" sx={{ mt: 5 }}>
            Course and certificates by MNAIR
          </Typography>
        </Container>

        <Snackbar open={!!copied} autoHideDuration={2000} onClose={() => setCopied(null)} message={`${copied} copied`} />
      </Box>
    </ThemeProvider>
  )
}

export default SponsorPortal
