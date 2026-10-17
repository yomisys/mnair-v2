import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  IconButton,
  LinearProgress,
  Link,
  Menu,
  MenuItem,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { ThemeProvider, useTheme } from '@mui/material/styles'
import {
  Send as SendIcon,
  MoreVert as MoreIcon,
  NotificationsActive as BellOnIcon,
  NotificationsNone as BellOffIcon,
  Telegram as TelegramIcon,
  Logout as LogoutIcon,
} from '@mui/icons-material'
import {
  learnAPI,
  LEARN_TOKEN_KEY,
  LearnConfig,
  LearnMessage,
  LearnProgress,
  LearnerSummary,
  SponsorBrandBase,
} from '../services/api'
import { BrandMark, brandTheme, SponsorAdvertCard } from '../components/SponsorBrand'

/**
 * Web learner app — the course as a chat, in the browser, with no messaging
 * app and no per-message cost. Talks to /api/v1/learn; every turn runs the
 * same ConversationEngine as the Telegram bot.
 */

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

/** Render the engine's *bold* markup safely (text is never injected as HTML). */
const renderMarkup = (text: string): React.ReactNode => {
  const parts = text.split(/(\*[^*\n]+\*)/g)
  return parts.map((part, i) =>
    part.startsWith('*') && part.endsWith('*') && part.length > 2
      ? <strong key={i}>{part.slice(1, -1)}</strong>
      : <React.Fragment key={i}>{part}</React.Fragment>,
  )
}

const urlBase64ToUint8Array = (base64: string): Uint8Array<ArrayBuffer> => {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = window.atob(b64)
  const out = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

const errorText = (e: unknown, fallback: string): string => {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg).replace(/^Value error, /, '')
  return fallback
}

// ---------------------------------------------------------------------------
// chat bubble
// ---------------------------------------------------------------------------

const Bubble: React.FC<{
  message: LearnMessage
  isLast: boolean
  onButton: (id: string, title: string, url?: string) => void
  busy: boolean
}> = ({ message, isLast, onButton, busy }) => {
  const fromUser = message.role === 'user'
  return (
    <Box sx={{ display: 'flex', justifyContent: fromUser ? 'flex-end' : 'flex-start', mb: 1.25 }}>
      <Box sx={{ maxWidth: { xs: '88%', sm: '75%' } }}>
        <Paper
          elevation={0}
          sx={{
            px: 2,
            py: 1.25,
            borderRadius: fromUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
            bgcolor: fromUser ? 'primary.main' : 'white',
            color: fromUser ? 'white' : 'text.primary',
            border: fromUser ? 'none' : '1px solid',
            borderColor: 'grey.200',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            fontSize: '0.98rem',
            lineHeight: 1.6,
          }}
        >
          {renderMarkup(message.text)}
        </Paper>
        {!fromUser && message.buttons?.length > 0 && isLast && (
          <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mt: 1 }}>
            {message.buttons.map((b) => {
              const isLink = /^https?:\/\//.test(b.description)
              const isAnswer = b.id.startsWith('ans_')
              return (
                <Chip
                  key={b.id}
                  label={isAnswer ? `${b.title}. ${b.description}` : b.title}
                  clickable
                  disabled={busy}
                  color={isAnswer ? 'default' : 'primary'}
                  variant={isAnswer ? 'outlined' : 'filled'}
                  onClick={() => onButton(b.id, b.title, isLink ? b.description : undefined)}
                  sx={{
                    height: 'auto',
                    py: 1,
                    fontWeight: 600,
                    '& .MuiChip-label': { whiteSpace: 'normal', textAlign: 'left', lineHeight: 1.35 },
                  }}
                />
              )
            })}
          </Stack>
        )}
      </Box>
    </Box>
  )
}

// ---------------------------------------------------------------------------
// sign-in / enrol
// ---------------------------------------------------------------------------

const AuthPanel: React.FC<{
  config: LearnConfig | null
  onAuthed: (messages: LearnMessage[], learner: LearnerSummary, state: string) => void
}> = ({ config, onAuthed }) => {
  const [tab, setTab] = useState<'enrol' | 'login'>('enrol')
  const [phone, setPhone] = useState('')
  const [pin, setPin] = useState('')
  const [name, setName] = useState('')
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Sponsor code from a join link (/learn?code=GRACE-7K2Q) or typed in
  const [sponsorCode, setSponsorCode] = useState(() => new URLSearchParams(window.location.search).get('code')?.toUpperCase() ?? '')
  const [sponsor, setSponsor] = useState<SponsorBrandBase | null>(null)
  const sponsorName = sponsor?.sponsor_name ?? null
  const base = useTheme()
  const sponsorTheme = useMemo(() => brandTheme(base, sponsor?.brand_color), [base, sponsor?.brand_color])
  const minPin = config?.pin_min_length ?? 4

  useEffect(() => {
    const code = sponsorCode.trim()
    setSponsor(null)
    if (code.length < 3) return
    const t = window.setTimeout(() => {
      learnAPI.brand(code).then(setSponsor).catch(() => setSponsor(null))
    }, 400)
    return () => window.clearTimeout(t)
  }, [sponsorCode])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (tab === 'enrol' && !consent) {
      setError('Please agree to the privacy notice to enrol.')
      return
    }
    setBusy(true)
    try {
      const auth = tab === 'enrol'
        ? await learnAPI.enrol(phone, pin, name, sponsorCode.trim())
        : await learnAPI.login(phone, pin)
      localStorage.setItem(LEARN_TOKEN_KEY, auth.access_token)
      onAuthed(auth.messages.map((m) => ({ ...m, role: 'bot' as const })), auth.learner, auth.state)
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (tab === 'enrol' && status === 409) {
        setTab('login')
        setError('This number is already enrolled — sign in with your PIN.')
      } else {
        setError(errorText(err, tab === 'enrol' ? 'Could not enrol. Check your number and try again.' : 'Sign-in failed.'))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Container maxWidth="xs" sx={{ py: 4 }}>
      <Paper elevation={0} sx={{ p: 3, border: '1px solid', borderColor: 'grey.200', borderRadius: 3 }}>
        <Typography variant="h5" fontWeight={800} gutterBottom>Learn AI in 7 days — free</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Lessons arrive here as a chat. Your phone number and a PIN are all you need to pick up where you left off on any device.
        </Typography>

        {sponsor && tab === 'enrol' && (
          <ThemeProvider theme={sponsorTheme}>
            <Stack
              direction="row"
              spacing={1.5}
              alignItems="center"
              sx={{ mb: 2, p: 1.5, borderRadius: 2, bgcolor: 'primary.main', color: 'primary.contrastText' }}
            >
              <BrandMark name={sponsor.sponsor_name} logoUrl={sponsor.logo_url} size={36} light />
              <Typography variant="body2">
                Your course and certificate are sponsored by <strong>{sponsor.sponsor_name}</strong>.
              </Typography>
            </Stack>
          </ThemeProvider>
        )}

        <Tabs value={tab} onChange={(_, v) => { setTab(v); setError(null) }} variant="fullWidth" sx={{ mb: 2 }}>
          <Tab label="New learner" value="enrol" />
          <Tab label="Sign in" value="login" />
        </Tabs>

        <Box component="form" onSubmit={submit}>
          <Stack spacing={2}>
            <TextField
              label="Phone number"
              placeholder="08031234567"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              inputProps={{ inputMode: 'tel', autoComplete: 'tel' }}
              required
              fullWidth
            />
            <TextField
              label={tab === 'enrol' ? `Choose a PIN (${minPin}+ digits)` : 'PIN'}
              type="password"
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 8))}
              inputProps={{ inputMode: 'numeric', pattern: '[0-9]*', autoComplete: tab === 'enrol' ? 'new-password' : 'current-password' }}
              helperText={tab === 'enrol' ? 'You will use this PIN to sign in later. Digits only.' : undefined}
              required
              fullWidth
            />
            {tab === 'enrol' && (
              <>
                <TextField
                  label="Your name (optional)"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  helperText="Only used on your certificate. You can add it later."
                  fullWidth
                />
                <TextField
                  label="Sponsor code (optional)"
                  value={sponsorCode}
                  onChange={(e) => setSponsorCode(e.target.value.toUpperCase())}
                  helperText={sponsorName ? `Sponsored by ${sponsorName}` : 'From your church, employer or school, if they gave you one.'}
                  inputProps={{ autoCapitalize: 'characters', maxLength: 40 }}
                  fullWidth
                />
                <Box
                  component="label"
                  sx={{ display: 'flex', gap: 1.25, alignItems: 'flex-start', cursor: 'pointer', fontSize: '0.85rem', color: 'text.secondary' }}
                >
                  <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} style={{ marginTop: 3 }} />
                  <span>
                    I agree that MNAIR stores my phone number and course progress to run this programme, in line with the
                    Nigeria Data Protection Act. No marketing, no selling of data. You can delete your account any time from the menu.
                  </span>
                </Box>
              </>
            )}
            {error && <Alert severity="error">{error}</Alert>}
            <Button type="submit" variant="contained" size="large" disabled={busy} sx={{ fontWeight: 700, py: 1.4 }}>
              {busy ? <CircularProgress size={22} color="inherit" /> : tab === 'enrol' ? 'Start Day 1' : 'Continue learning'}
            </Button>
          </Stack>
        </Box>

        {config?.telegram_link && (
          <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid', borderColor: 'grey.200', textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>Prefer Telegram?</Typography>
            <Button
              variant="outlined"
              startIcon={<TelegramIcon />}
              href={config.telegram_link}
              target="_blank"
              rel="noopener noreferrer"
              sx={{ borderColor: '#229ED9', color: '#229ED9', fontWeight: 700 }}
            >
              Open the MNAIR bot
            </Button>
          </Box>
        )}
        <Typography variant="caption" color="text.secondary" display="block" align="center" sx={{ mt: 2 }}>
          No internet? Dial <strong>{config?.ussd_code ?? '*384*8080#'}</strong>
        </Typography>
      </Paper>
      {sponsor?.advert && tab === 'enrol' && (
        <ThemeProvider theme={sponsorTheme}>
          <Box sx={{ mt: 2 }}>
            <SponsorAdvertCard advert={sponsor.advert} sponsorName={sponsor.sponsor_name} variant="compact" />
          </Box>
        </ThemeProvider>
      )}
    </Container>
  )
}

// ---------------------------------------------------------------------------
// main page
// ---------------------------------------------------------------------------

const Learn: React.FC = () => {
  const navigate = useNavigate()
  const [config, setConfig] = useState<LearnConfig | null>(null)
  const [authed, setAuthed] = useState<boolean>(() => !!localStorage.getItem(LEARN_TOKEN_KEY))
  const [loading, setLoading] = useState(true)
  const [messages, setMessages] = useState<LearnMessage[]>([])
  const [learner, setLearner] = useState<LearnerSummary | null>(null)
  const [progress, setProgress] = useState<LearnProgress | null>(null)
  const [state, setState] = useState<string>('')
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pushOn, setPushOn] = useState(false)
  const [pushSupported, setPushSupported] = useState(false)
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null)
  const [sponsor, setSponsor] = useState<SponsorBrandBase | null>(null)
  const [adHidden, setAdHidden] = useState(() => {
    try { return sessionStorage.getItem('learn_ad_hidden') === '1' } catch { return false }
  })
  const base = useTheme()
  const sponsorTheme = useMemo(() => brandTheme(base, sponsor?.brand_color), [base, sponsor?.brand_color])
  const bottomRef = useRef<HTMLDivElement | null>(null)

  const loadSponsor = useCallback(() => {
    learnAPI.mySponsor().then((r) => setSponsor(r.sponsor)).catch(() => setSponsor(null))
  }, [])

  useEffect(() => {
    if (authed) loadSponsor()
    else setSponsor(null)
  }, [authed, loadSponsor])

  const hideAd = () => {
    setAdHidden(true)
    try { sessionStorage.setItem('learn_ad_hidden', '1') } catch { /* private mode */ }
  }

  // Service worker (offline shell + push handler). Registration is best-effort.
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => { /* ignore */ })
    }
    setPushSupported('serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window)
  }, [])

  useEffect(() => {
    learnAPI.getConfig().then(setConfig).catch(() => setConfig(null))
  }, [])

  const restore = useCallback(async () => {
    setLoading(true)
    try {
      const s = await learnAPI.getState()
      setMessages(s.history)
      setLearner(s.learner)
      setProgress(s.progress)
      setState(s.state)
      setPushOn(s.push_subscribed)
      if (s.history.length === 0) {
        // Brand-new thread (e.g. token from an old session): kick it off
        const turn = await learnAPI.send({ text: 'START' })
        setMessages(turn.messages.map((m) => ({ ...m, role: 'bot' as const })))
        setState(turn.state)
      }
    } catch {
      localStorage.removeItem(LEARN_TOKEN_KEY)
      setAuthed(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (authed) restore()
    else setLoading(false)
  }, [authed, restore])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, busy])

  const sendTurn = async (payload: { text?: string; interactive_id?: string }, echo: string) => {
    if (busy) return
    setBusy(true)
    setError(null)
    setMessages((prev) => [...prev, { kind: 'text', text: echo, buttons: [], meta: {}, role: 'user' }])
    try {
      const turn = await learnAPI.send(payload)
      setMessages((prev) => [...prev, ...turn.messages.map((m) => ({ ...m, role: 'bot' as const }))])
      setLearner(turn.learner)
      setProgress(turn.progress)
      setState(turn.state)
    } catch (e) {
      const status = (e as { response?: { status?: number } })?.response?.status
      if (status === 401) {
        localStorage.removeItem(LEARN_TOKEN_KEY)
        setAuthed(false)
        return
      }
      setError(errorText(e, 'Could not reach MNAIR. Check your connection and try again.'))
    } finally {
      setBusy(false)
    }
  }

  const onButton = (id: string, title: string, url?: string) => {
    if (url) {
      window.open(url, '_blank', 'noopener')
      return
    }
    sendTurn({ interactive_id: id }, title.replace(/^[^\w]+/, '').trim() || title)
  }

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const text = input.trim()
    if (!text) return
    setInput('')
    sendTurn({ text }, text)
  }

  const togglePush = async () => {
    setMenuAnchor(null)
    if (!pushSupported) return
    try {
      const reg = await navigator.serviceWorker.ready
      if (pushOn) {
        const sub = await reg.pushManager.getSubscription()
        if (sub) {
          await learnAPI.unsubscribePush(sub.endpoint)
          await sub.unsubscribe()
        }
        setPushOn(false)
        return
      }
      if (!config?.vapid_public_key) {
        setError('Reminders are not configured on this server yet.')
        return
      }
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') return
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(config.vapid_public_key),
      })
      await learnAPI.subscribePush(sub.toJSON())
      setPushOn(true)
    } catch {
      setError('Could not turn on reminders on this device.')
    }
  }

  const enterSponsorCode = () => {
    setMenuAnchor(null)
    const code = window.prompt('Enter the sponsor code you were given:')?.trim()
    if (code) sendTurn({ text: `CODE ${code}` }, `Sponsor code ${code.toUpperCase()}`).then(loadSponsor)
  }

  const signOut = () => {
    setMenuAnchor(null)
    localStorage.removeItem(LEARN_TOKEN_KEY)
    setMessages([])
    setLearner(null)
    setAuthed(false)
  }

  const forgetMe = async () => {
    setMenuAnchor(null)
    if (!window.confirm('Delete your MNAIR account and all progress? This cannot be undone.')) return
    try {
      await learnAPI.forgetMe()
    } finally {
      signOut()
    }
  }

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 10 }}>
        <CircularProgress />
      </Box>
    )
  }

  if (!authed) {
    return (
      <AuthPanel
        config={config}
        onAuthed={(msgs, l, s) => {
          setMessages(msgs)
          setLearner(l)
          setState(s)
          setAuthed(true)
        }}
      />
    )
  }

  const pct = progress ? Math.round(progress.completion_percentage) : 0
  const lastBotIndex = (() => {
    for (let i = messages.length - 1; i >= 0; i--) if (messages[i].role !== 'user') return i
    return -1
  })()

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 64px)', bgcolor: '#f3f5f7' }}>
      {/* header */}
      <Box sx={{ bgcolor: 'white', borderBottom: '1px solid', borderColor: 'grey.200', px: 2, py: 1 }}>
        <Container maxWidth="sm" disableGutters>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography fontWeight={800} noWrap>
                Day {learner?.current_day ?? 1} of 7
                {learner?.name_confirmed ? ` · ${learner.name}` : ''}
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap>
                {progress ? `${progress.lessons_completed}/${progress.total_lessons} lessons · ${pct}% complete` : 'Free AI literacy course'}
              </Typography>
            </Box>
            {pushSupported && (
              <Tooltip title={pushOn ? 'Daily reminders on' : 'Turn on daily reminders'}>
                <IconButton onClick={togglePush} color={pushOn ? 'primary' : 'default'} size="small">
                  {pushOn ? <BellOnIcon /> : <BellOffIcon />}
                </IconButton>
              </Tooltip>
            )}
            <IconButton size="small" onClick={(e) => setMenuAnchor(e.currentTarget)} aria-label="menu">
              <MoreIcon />
            </IconButton>
            <Menu anchorEl={menuAnchor} open={!!menuAnchor} onClose={() => setMenuAnchor(null)}>
              <MenuItem onClick={() => { setMenuAnchor(null); sendTurn({ text: 'PROGRESS' }, 'Progress') }}>My progress</MenuItem>
              <MenuItem onClick={() => { setMenuAnchor(null); sendTurn({ text: 'LANGUAGE' }, 'Change language') }}>Change language</MenuItem>
              {pushSupported && <MenuItem onClick={togglePush}>{pushOn ? 'Turn off reminders' : 'Turn on reminders'}</MenuItem>}
              <MenuItem onClick={enterSponsorCode}>Enter a sponsor code</MenuItem>
              <MenuItem onClick={() => { setMenuAnchor(null); navigate('/verify') }}>Verify a certificate</MenuItem>
              <MenuItem onClick={signOut}><LogoutIcon fontSize="small" sx={{ mr: 1 }} /> Sign out</MenuItem>
              <MenuItem onClick={forgetMe} sx={{ color: 'error.main' }}>Delete my account</MenuItem>
            </Menu>
          </Stack>
        </Container>
        <LinearProgress variant="determinate" value={pct} sx={{ mt: 1, height: 4, borderRadius: 2 }} />
      </Box>

      {/* thread */}
      <Box sx={{ flex: 1, overflowY: 'auto', px: 2, py: 2 }}>
        <Container maxWidth="sm" disableGutters>
          {sponsor?.advert && !adHidden && (
            <ThemeProvider theme={sponsorTheme}>
              <Box sx={{ mb: 2 }}>
                <SponsorAdvertCard advert={sponsor.advert} sponsorName={sponsor.sponsor_name} variant="compact" onDismiss={hideAd} />
              </Box>
            </ThemeProvider>
          )}
          {messages.map((m, i) => (
            <Bubble key={i} message={m} isLast={i === lastBotIndex} onButton={onButton} busy={busy} />
          ))}
          {busy && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, color: 'text.secondary', fontSize: '0.85rem', mb: 1 }}>
              <CircularProgress size={14} /> MNAIR is typing…
            </Box>
          )}
          {error && <Alert severity="warning" onClose={() => setError(null)} sx={{ mb: 1 }}>{error}</Alert>}
          <div ref={bottomRef} />
        </Container>
      </Box>

      {/* composer */}
      <Box component="form" onSubmit={onSubmit} sx={{ bgcolor: 'white', borderTop: '1px solid', borderColor: 'grey.200', p: 1.5 }}>
        <Container maxWidth="sm" disableGutters>
          <Stack direction="row" spacing={1}>
            <TextField
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={state === 'awaiting_certificate_name' ? 'Type your full name' : 'Type a reply (e.g. QUIZ, NEXT, A)…'}
              size="small"
              fullWidth
              disabled={busy}
              inputProps={{ maxLength: 1000, 'aria-label': 'message' }}
            />
            <Button type="submit" variant="contained" disabled={busy || !input.trim()} sx={{ minWidth: 48, px: 1.5 }} aria-label="send">
              <SendIcon />
            </Button>
          </Stack>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            Tap the buttons above, or type. Progress is saved after every step — you can close this page and{' '}
            <Link component="button" type="button" onClick={() => sendTurn({ text: 'CONTINUE' }, 'Continue')} sx={{ verticalAlign: 'baseline' }}>
              continue
            </Link>{' '}
            any time.
          </Typography>
        </Container>
      </Box>
    </Box>
  )
}

export default Learn
