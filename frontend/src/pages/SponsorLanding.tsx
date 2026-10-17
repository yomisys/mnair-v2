import React, { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  alpha,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Grid,
  Link,
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import { ThemeProvider, useTheme } from '@mui/material/styles'
import {
  AccessTime as TimeIcon,
  PhoneAndroid as PhoneIcon,
  Telegram as TelegramIcon,
  VerifiedUser as CertIcon,
  Translate as LanguageIcon,
  ArrowForward as ArrowIcon,
  FormatQuote as QuoteIcon,
} from '@mui/icons-material'
import { learnAPI, SponsorBrand } from '../services/api'
import { BrandMark, brandTheme, SponsorAdvertCard } from '../components/SponsorBrand'

/**
 * White-label landing page for one sponsor code: /s/GRACE-7K2Q.
 * The sponsor's name, colour, logo, welcome note and advert lead; MNAIR
 * only appears as a small "course by" credit in the footer.
 */

const DAYS = [
  { day: 1, title: 'Meet AI', blurb: 'What AI is, how it "thinks", and where you already use it.' },
  { day: 2, title: 'AI at Work', blurb: 'How machines learn, automation, and what it means for jobs.' },
  { day: 3, title: 'AI in Nigeria', blurb: 'Local apps in farming, fintech, health and education.' },
  { day: 4, title: 'AI Tools', blurb: 'Chat assistants, image, voice and translation tools you can try today.' },
  { day: 5, title: 'AI Ethics', blurb: 'Bias, privacy, fake news, and your rights.' },
  { day: 6, title: 'Building with AI', blurb: 'Putting AI to work in business, farming, finance and health.' },
  { day: 7, title: 'Your AI Future', blurb: 'Stay current, teach others, final quiz — and your certificate.' },
]

const FEATURES = [
  { icon: <TimeIcon />, title: '10 minutes a day', text: 'Five short lessons a day for seven days.' },
  { icon: <PhoneIcon />, title: 'Any phone', text: 'Learn in your browser or on Telegram. Very little data.' },
  { icon: <LanguageIcon />, title: 'Your language', text: 'English, Pidgin, Hausa, Yoruba or Igbo.' },
  { icon: <CertIcon />, title: 'Verified certificate', text: 'Free for you, and anyone can check it online.' },
]

const NotFound: React.FC = () => (
  <Container maxWidth="sm" sx={{ py: 12, textAlign: 'center' }}>
    <Typography variant="h4" fontWeight={800} gutterBottom>This link isn't active</Typography>
    <Typography color="text.secondary" sx={{ mb: 3 }}>
      The sponsor code may have expired or been switched off. Ask whoever shared it for a new link, or start the free course anyway.
    </Typography>
    <Button variant="contained" size="large" href="/learn">Start learning</Button>
  </Container>
)

const Landing: React.FC<{ brand: SponsorBrand }> = ({ brand }) => {
  const theme = useTheme()
  const joinPath = `/learn?code=${encodeURIComponent(brand.code)}`
  const brandMain = theme.palette.primary.main
  const onBrand = theme.palette.primary.contrastText
  const heroBg = `linear-gradient(135deg, ${theme.palette.primary.dark} 0%, ${brandMain} 55%, ${theme.palette.primary.light} 100%)`

  const startButtons = (inverted: boolean) => (
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
      <Button
        href={joinPath}
        size="large"
        variant="contained"
        endIcon={<ArrowIcon />}
        sx={{
          fontWeight: 800, borderRadius: 99, px: 4, py: 1.5, boxShadow: 'none', fontSize: '1.05rem',
          ...(inverted && { bgcolor: onBrand, color: brandMain, '&:hover': { bgcolor: alpha(onBrand, 0.9) } }),
        }}
      >
        Start learning free
      </Button>
      {brand.telegram_url && (
        <Button
          href={brand.telegram_url}
          target="_blank"
          rel="noopener noreferrer"
          size="large"
          variant="outlined"
          startIcon={<TelegramIcon />}
          sx={{
            fontWeight: 700, borderRadius: 99, px: 3, py: 1.5,
            ...(inverted && { color: onBrand, borderColor: alpha(onBrand, 0.6), '&:hover': { borderColor: onBrand, bgcolor: alpha(onBrand, 0.08) } }),
          }}
        >
          Use Telegram
        </Button>
      )}
    </Stack>
  )

  return (
    <Box sx={{ bgcolor: '#FAFAF7', minHeight: '100vh', color: '#1A1A1A' }}>
      {/* top bar */}
      <Box
        component="header"
        sx={{
          position: 'sticky', top: 0, zIndex: 10, bgcolor: alpha('#FFFFFF', 0.92), backdropFilter: 'blur(8px)',
          borderBottom: '1px solid', borderColor: 'grey.200',
        }}
      >
        <Container maxWidth="lg">
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ py: 1.25 }}>
            <BrandMark name={brand.sponsor_name} logoUrl={brand.logo_url} size={40} />
            <Typography fontWeight={800} noWrap sx={{ flex: 1, minWidth: 0, fontSize: '1.05rem' }}>
              {brand.sponsor_name}
            </Typography>
            <Button href={joinPath} variant="contained" sx={{ borderRadius: 99, fontWeight: 700, boxShadow: 'none', flexShrink: 0 }}>
              Start
            </Button>
          </Stack>
        </Container>
      </Box>

      {/* hero */}
      <Box sx={{ background: heroBg, color: onBrand, position: 'relative', overflow: 'hidden' }}>
        <Box
          aria-hidden
          sx={{
            position: 'absolute', right: -120, top: -120, width: 420, height: 420, borderRadius: '50%',
            bgcolor: alpha(onBrand, 0.07),
          }}
        />
        <Container maxWidth="lg" sx={{ py: { xs: 7, md: 11 }, position: 'relative' }}>
          <Grid container spacing={{ xs: 5, md: 8 }} alignItems="center">
            <Grid item xs={12} md={7}>
              <Chip
                label={`Free for you · Sponsored by ${brand.sponsor_name}`}
                sx={{
                  bgcolor: alpha(onBrand, 0.14), color: onBrand, fontWeight: 700, mb: 3, maxWidth: '100%',
                  height: 'auto', py: 0.5, '& .MuiChip-label': { whiteSpace: 'normal' },
                }}
              />
              <Typography
                component="h1"
                sx={{ fontWeight: 900, fontSize: { xs: '2.4rem', md: '3.6rem' }, lineHeight: 1.05, letterSpacing: '-0.02em' }}
              >
                Learn AI in 7 days.
                <Box component="span" sx={{ display: 'block', opacity: 0.85 }}>On us.</Box>
              </Typography>
              <Typography sx={{ mt: 2.5, fontSize: { xs: '1.1rem', md: '1.3rem' }, opacity: 0.92, maxWidth: 560 }}>
                {brand.tagline || `${brand.sponsor_name} is covering your course and certificate. Ten minutes a day, on any phone.`}
              </Typography>
              <Box sx={{ mt: 4 }}>{startButtons(true)}</Box>
            </Grid>
            <Grid item xs={12} md={5}>
              <Paper
                elevation={0}
                sx={{ p: { xs: 3, md: 4 }, borderRadius: 4, bgcolor: '#FFFFFF', color: '#1A1A1A', boxShadow: '0 24px 60px rgba(0,0,0,0.18)' }}
              >
                <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2.5 }}>
                  <BrandMark name={brand.sponsor_name} logoUrl={brand.logo_url} size={56} />
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="overline" color="text.secondary" sx={{ lineHeight: 1.4 }}>A message from</Typography>
                    <Typography fontWeight={800} sx={{ fontSize: '1.1rem', lineHeight: 1.25 }}>{brand.sponsor_name}</Typography>
                  </Box>
                </Stack>
                <Box sx={{ position: 'relative', pl: 4 }}>
                  <QuoteIcon sx={{ position: 'absolute', left: -4, top: -6, color: 'primary.main', fontSize: 32, opacity: 0.6 }} />
                  <Typography sx={{ whiteSpace: 'pre-line', fontSize: '1.02rem', lineHeight: 1.65 }}>
                    {brand.welcome_message ||
                      'AI is changing how we work, farm, trade and learn. We want every one of our people to be ready, so this course is on us.'}
                  </Typography>
                </Box>
                <Box sx={{ mt: 3, pt: 2.5, borderTop: '1px dashed', borderColor: 'grey.300' }}>
                  <Typography variant="caption" color="text.secondary" display="block">Your sponsor code</Typography>
                  <Typography sx={{ fontFamily: 'monospace', fontWeight: 800, fontSize: '1.35rem', letterSpacing: 2, color: 'primary.main' }}>
                    {brand.code}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">Already applied when you start from this page.</Typography>
                </Box>
              </Paper>
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* features */}
      <Container maxWidth="lg" sx={{ mt: { xs: -3, md: -5 }, position: 'relative' }}>
        <Paper elevation={0} sx={{ borderRadius: 4, border: '1px solid', borderColor: 'grey.200', bgcolor: 'white', p: { xs: 2.5, md: 3.5 } }}>
          <Grid container spacing={3}>
            {FEATURES.map((f) => (
              <Grid item xs={12} sm={6} md={3} key={f.title}>
                <Stack direction="row" spacing={1.5} alignItems="flex-start">
                  <Box
                    sx={{
                      width: 44, height: 44, borderRadius: 2.5, flexShrink: 0, display: 'grid', placeItems: 'center',
                      bgcolor: alpha(brandMain, 0.1), color: 'primary.main',
                    }}
                  >
                    {f.icon}
                  </Box>
                  <Box>
                    <Typography fontWeight={800}>{f.title}</Typography>
                    <Typography variant="body2" color="text.secondary">{f.text}</Typography>
                  </Box>
                </Stack>
              </Grid>
            ))}
          </Grid>
        </Paper>
      </Container>

      {/* sponsor advert */}
      {brand.advert && (
        <Container maxWidth="lg" sx={{ mt: { xs: 6, md: 9 } }}>
          <SponsorAdvertCard advert={brand.advert} sponsorName={brand.sponsor_name} />
        </Container>
      )}

      {/* curriculum */}
      <Container maxWidth="lg" sx={{ mt: { xs: 7, md: 10 } }}>
        <Typography variant="overline" sx={{ color: 'primary.main', fontWeight: 800, letterSpacing: 1.5 }}>The course</Typography>
        <Typography component="h2" sx={{ fontWeight: 900, fontSize: { xs: '1.9rem', md: '2.5rem' }, letterSpacing: '-0.01em', mb: 4 }}>
          Seven days, from "what is AI?" to certified
        </Typography>
        <Grid container spacing={2}>
          {DAYS.map((d) => (
            <Grid item xs={12} sm={6} md={d.day === 7 ? 12 : 4} lg={d.day === 7 ? 6 : 3} key={d.day}>
              <Paper
                elevation={0}
                sx={{
                  p: 2.5, height: '100%', borderRadius: 3, border: '1px solid', borderColor: 'grey.200', bgcolor: 'white',
                  ...(d.day === 7 && { bgcolor: alpha(brandMain, 0.06), borderColor: alpha(brandMain, 0.3) }),
                }}
              >
                <Typography sx={{ color: 'primary.main', fontWeight: 900, fontSize: '0.8rem', letterSpacing: 1 }}>DAY {d.day}</Typography>
                <Typography fontWeight={800} sx={{ fontSize: '1.15rem', mt: 0.5 }}>{d.title}</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>{d.blurb}</Typography>
              </Paper>
            </Grid>
          ))}
        </Grid>
      </Container>

      {/* how it works */}
      <Container maxWidth="lg" sx={{ mt: { xs: 7, md: 10 } }}>
        <Grid container spacing={3}>
          {[
            { n: '1', t: 'Tap "Start learning free"', d: 'Enter your phone number and choose a PIN. Your sponsor code is already filled in.' },
            { n: '2', t: 'Learn for 10 minutes a day', d: 'Lessons arrive as a chat. Stop any time; your progress is saved.' },
            { n: '3', t: 'Get your certificate', d: `Pass the final quiz and get a verified certificate, paid for by ${brand.sponsor_name}.` },
          ].map((s) => (
            <Grid item xs={12} md={4} key={s.n}>
              <Stack direction="row" spacing={2}>
                <Box
                  sx={{
                    width: 40, height: 40, borderRadius: '50%', flexShrink: 0, display: 'grid', placeItems: 'center',
                    bgcolor: 'primary.main', color: 'primary.contrastText', fontWeight: 900,
                  }}
                >
                  {s.n}
                </Box>
                <Box>
                  <Typography fontWeight={800} sx={{ fontSize: '1.05rem' }}>{s.t}</Typography>
                  <Typography color="text.secondary" sx={{ mt: 0.5 }}>{s.d}</Typography>
                </Box>
              </Stack>
            </Grid>
          ))}
        </Grid>
      </Container>

      {/* closing call to action */}
      <Container maxWidth="lg" sx={{ mt: { xs: 7, md: 10 } }}>
        <Box sx={{ background: heroBg, color: onBrand, borderRadius: 5, p: { xs: 4, md: 7 }, textAlign: { xs: 'left', md: 'center' } }}>
          <Typography component="h2" sx={{ fontWeight: 900, fontSize: { xs: '1.8rem', md: '2.4rem' }, lineHeight: 1.15 }}>
            Your seat is paid for. Start today.
          </Typography>
          <Typography sx={{ mt: 1.5, opacity: 0.9, fontSize: '1.1rem' }}>
            It's free for you. {brand.sponsor_name} is covering the course and your certificate.
          </Typography>
          <Box sx={{ mt: 3.5, display: 'flex', justifyContent: { xs: 'flex-start', md: 'center' } }}>{startButtons(true)}</Box>
        </Box>
      </Container>

      {/* footer */}
      <Box component="footer" sx={{ mt: { xs: 7, md: 10 }, py: 4, borderTop: '1px solid', borderColor: 'grey.200', bgcolor: 'white' }}>
        <Container maxWidth="lg">
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ xs: 'flex-start', md: 'center' }} justifyContent="space-between">
            <Stack direction="row" spacing={1.5} alignItems="center">
              <BrandMark name={brand.sponsor_name} logoUrl={brand.logo_url} size={32} />
              <Box>
                <Typography fontWeight={800}>{brand.sponsor_name}</Typography>
                {brand.website_url && (
                  <Link href={brand.website_url} target="_blank" rel="noopener noreferrer" variant="body2" underline="hover">
                    {brand.website_url.replace(/^https?:\/\//, '').replace(/\/$/, '')}
                  </Link>
                )}
              </Box>
            </Stack>
            <Typography variant="caption" color="text.secondary">
              Course and certificates by <Link href="/" color="inherit" underline="hover">MNAIR</Link> ·{' '}
              <Link href="/verify" color="inherit" underline="hover">Verify a certificate</Link>
            </Typography>
          </Stack>
        </Container>
      </Box>
    </Box>
  )
}

const SponsorLanding: React.FC = () => {
  const { code = '' } = useParams()
  const base = useTheme()
  const [brand, setBrand] = useState<SponsorBrand | null>(null)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    learnAPI.brand(code).then(setBrand).catch(() => setMissing(true))
  }, [code])

  useEffect(() => {
    if (brand) document.title = `${brand.sponsor_name} · Free AI course`
  }, [brand])

  const theme = useMemo(() => brandTheme(base, brand?.brand_color), [base, brand?.brand_color])

  if (missing) return <NotFound />
  if (!brand) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 14 }}>
        <CircularProgress />
      </Box>
    )
  }
  return (
    <ThemeProvider theme={theme}>
      <Landing brand={brand} />
    </ThemeProvider>
  )
}

export default SponsorLanding
