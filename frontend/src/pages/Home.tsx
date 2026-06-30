import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box,
  Button,
  Container,
  Grid,
  Typography,
  Card,
  CardContent,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Divider,
  Link,
  Tooltip,
  Chip,
} from '@mui/material'
import {
  WhatsApp as WhatsAppIcon,
  Message as MessageIcon,
  Dialpad as DialpadIcon,
  CheckCircle as CheckIcon,
  EmojiEvents as TrophyIcon,
  ArrowForward as ArrowIcon,
} from '@mui/icons-material'

const WHATSAPP_NUMBER = '+234 706 572 8972'
const WHATSAPP_LINK = `https://wa.me/${WHATSAPP_NUMBER.replace(/[^0-9]/g, '')}?text=START`

const DAYS = [
  { day: 1, title: 'Meet AI', color: '#1B5E20', topics: ['What is AI?', 'How AI Thinks', 'AI Around You', 'AI Tools Intro', 'AI & Society'] },
  { day: 2, title: 'AI at Work', color: '#2E7D32', topics: ['How AI Learns', 'Machine Learning', 'AI in Business', 'Automation', 'AI & Jobs'] },
  { day: 3, title: 'AI in Nigeria', color: '#388E3C', topics: ['Local AI Apps', 'Agritech & AI', 'Fintech & AI', 'Healthcare AI', 'Education AI'] },
  { day: 4, title: 'AI Tools', color: '#43A047', topics: ['ChatGPT & More', 'Image AI', 'Voice AI', 'Translation AI', 'Productivity AI'] },
  { day: 5, title: 'AI Ethics', color: '#2E7D32', topics: ['Bias in AI', 'Privacy & Data', 'Fake News & AI', 'AI Fairness', 'Your AI Rights'] },
  { day: 6, title: 'Building with AI', color: '#388E3C', topics: ['AI for Business', 'AI & Farming', 'AI & Finance', 'AI & Health', 'AI Careers'] },
  { day: 7, title: 'Your AI Future', color: '#1B5E20', topics: ['AI Strategy', 'Staying Current', 'Teaching Others', 'Final Quiz', '🎓 Earn Certificate'] },
]

const LANGUAGES = [
  { code: 'en', name: 'English', native: 'English' },
  { code: 'pid', name: 'Pidgin', native: 'Naija' },
  { code: 'ha', name: 'Hausa', native: 'Hausa' },
  { code: 'yo', name: 'Yoruba', native: 'Yorùbá' },
  { code: 'ig', name: 'Igbo', native: 'Igbo' },
]

const ChatBubble: React.FC<{ text: string; from: 'bot' | 'user' }> = ({ text, from }) => (
  <Box
    sx={{
      display: 'flex',
      justifyContent: from === 'user' ? 'flex-end' : 'flex-start',
      mb: 1,
    }}
  >
    <Box
      sx={{
        maxWidth: '78%',
        px: 1.5,
        py: 0.8,
        borderRadius: from === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
        bgcolor: from === 'user' ? '#DCF8C6' : 'white',
        color: '#111',
        fontSize: '0.72rem',
        lineHeight: 1.4,
        boxShadow: '0 1px 2px rgba(0,0,0,0.15)',
      }}
    >
      {text}
    </Box>
  </Box>
)

const Home: React.FC = () => {
  const navigate = useNavigate()
  const [openDialog, setOpenDialog] = useState(false)

  return (
    <Box>
      {/* ── HERO ── */}
      <Box
        sx={{
          background: 'linear-gradient(135deg, #1a5c2a 0%, #1B7A3E 50%, #0d4a1f 100%)',
          color: 'white',
          pt: { xs: 7, md: 10 },
          pb: { xs: 6, md: 0 },
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {/* decorative circles */}
        <Box sx={{ position: 'absolute', top: -80, right: -80, width: 300, height: 300, borderRadius: '50%', bgcolor: 'rgba(255,255,255,0.04)', pointerEvents: 'none' }} />
        <Box sx={{ position: 'absolute', bottom: 60, left: -60, width: 200, height: 200, borderRadius: '50%', bgcolor: 'rgba(255,255,255,0.03)', pointerEvents: 'none' }} />

        <Container maxWidth="lg">
          <Grid container spacing={4} alignItems="center">
            {/* Left: copy */}
            <Grid item xs={12} md={6}>
              <Chip
                label="🇳🇬  Nigeria's AI Literacy Program"
                sx={{ bgcolor: 'rgba(255,255,255,0.15)', color: 'white', fontWeight: 600, mb: 3, fontSize: '0.8rem' }}
              />
              <Typography
                variant="h1"
                fontWeight={800}
                sx={{ fontSize: { xs: '2.4rem', md: '3.6rem' }, lineHeight: 1.1, mb: 2 }}
              >
                Make Nigeria<br />AI Ready
              </Typography>
              <Typography sx={{ fontSize: '1.1rem', opacity: 0.88, mb: 1, lineHeight: 1.7 }}>
                A free 7-day AI literacy program delivered straight to your WhatsApp — in your language, at your pace.
              </Typography>
              <Typography sx={{ fontSize: '0.95rem', opacity: 0.7, mb: 4 }}>
                No data charges. No prerequisites. Earn a verifiable certificate.
              </Typography>

              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <Button
                  variant="contained"
                  size="large"
                  startIcon={<WhatsAppIcon />}
                  onClick={() => setOpenDialog(true)}
                  sx={{
                    bgcolor: '#25D366',
                    color: 'white',
                    fontWeight: 700,
                    fontSize: '1rem',
                    px: 3.5,
                    py: 1.5,
                    borderRadius: 2,
                    '&:hover': { bgcolor: '#1ebe57' },
                  }}
                >
                  Start on WhatsApp — Free
                </Button>
                <Button
                  variant="outlined"
                  size="large"
                  onClick={() => navigate('/verify')}
                  sx={{
                    borderColor: 'rgba(255,255,255,0.5)',
                    color: 'white',
                    fontWeight: 600,
                    px: 3,
                    py: 1.5,
                    borderRadius: 2,
                    '&:hover': { borderColor: 'white', bgcolor: 'rgba(255,255,255,0.08)' },
                  }}
                >
                  Verify Certificate
                </Button>
              </Stack>
            </Grid>

            {/* Right: WhatsApp phone mockup */}
            <Grid item xs={12} md={6} sx={{ display: 'flex', justifyContent: 'center', pb: { xs: 0, md: 0 } }}>
              <Box
                sx={{
                  width: 260,
                  borderRadius: 4,
                  overflow: 'hidden',
                  boxShadow: '0 32px 80px rgba(0,0,0,0.4)',
                  mb: { xs: 0, md: '-4px' },
                  mt: { xs: 4, md: 0 },
                }}
              >
                {/* phone header */}
                <Box sx={{ bgcolor: '#075E54', px: 2, py: 1.5, display: 'flex', alignItems: 'center', gap: 1.5 }}>
                  <Box sx={{ width: 34, height: 34, borderRadius: '50%', bgcolor: '#25D366', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <WhatsAppIcon sx={{ fontSize: 18, color: 'white' }} />
                  </Box>
                  <Box>
                    <Typography sx={{ color: 'white', fontWeight: 700, fontSize: '0.82rem', lineHeight: 1.2 }}>MNAIR</Typography>
                    <Typography sx={{ color: 'rgba(255,255,255,0.65)', fontSize: '0.68rem' }}>AI Literacy Program</Typography>
                  </Box>
                </Box>
                {/* chat body */}
                <Box sx={{ bgcolor: '#ECE5DD', p: 1.5, minHeight: 300 }}>
                  <ChatBubble from="bot" text="👋 Welcome to MNAIR! Nigeria's free AI literacy program." />
                  <ChatBubble from="bot" text="Which language do you prefer? Reply with a number:" />
                  <ChatBubble from="bot" text={"1. English\n2. Naija Pidgin\n3. Hausa\n4. Yorùbá\n5. Igbo"} />
                  <ChatBubble from="user" text="1" />
                  <ChatBubble from="bot" text="Great! Starting Day 1 🚀" />
                  <ChatBubble from="bot" text="📚 Lesson 1: What is Artificial Intelligence?" />
                  <ChatBubble from="bot" text="AI is when computers do things that normally need human thinking — like recognizing your face or translating languages." />
                  <ChatBubble from="user" text="Wow, that's cool!" />
                  <ChatBubble from="bot" text="Ready for the quiz? Type YES to continue ✅" />
                </Box>
              </Box>
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* ── STATS STRIP ── */}
      <Box sx={{ bgcolor: 'white', borderBottom: '1px solid', borderColor: 'grey.100', py: 0 }}>
        <Container maxWidth="lg">
          <Grid container>
            {[
              { value: '175', label: 'Lessons' },
              { value: '5', label: 'Languages' },
              { value: '7', label: 'Days' },
              { value: '₦0', label: 'Cost' },
            ].map((stat, i) => (
              <Grid item xs={3} key={i}>
                <Box
                  sx={{
                    py: 3,
                    textAlign: 'center',
                    borderRight: i < 3 ? '1px solid' : 'none',
                    borderColor: 'grey.100',
                  }}
                >
                  <Typography variant="h4" fontWeight={800} color="primary.main" sx={{ lineHeight: 1 }}>
                    {stat.value}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.75rem' }}>
                    {stat.label}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* ── HOW IT WORKS ── */}
      <Box sx={{ bgcolor: 'grey.50', py: { xs: 7, md: 10 } }}>
        <Container maxWidth="md">
          <Typography variant="overline" color="primary" fontWeight={700} display="block" align="center" sx={{ mb: 1, letterSpacing: 2 }}>
            HOW IT WORKS
          </Typography>
          <Typography variant="h3" fontWeight={800} align="center" gutterBottom sx={{ mb: 1 }}>
            3 Simple Steps
          </Typography>
          <Typography align="center" color="text.secondary" sx={{ mb: 7 }}>
            From zero to AI-certified in one week
          </Typography>

          <Grid container spacing={3} alignItems="flex-start">
            {[
              {
                step: '01',
                title: 'Send "START" on WhatsApp',
                desc: `Message ${WHATSAPP_NUMBER} with the word START. No app download. No signup. No data charge.`,
                icon: <WhatsAppIcon sx={{ fontSize: 28, color: '#25D366' }} />,
              },
              {
                step: '02',
                title: 'Pick Your Language',
                desc: 'Choose from English, Pidgin, Hausa, Yoruba, or Igbo. The lessons come to you in your own language.',
                icon: <Box sx={{ fontSize: 28 }}>🗣️</Box>,
              },
              {
                step: '03',
                title: 'Learn & Earn Your Certificate',
                desc: '5 lessons per day, 10 minutes each. Pass the daily quiz and collect your certificate after Day 7.',
                icon: <TrophyIcon sx={{ fontSize: 28, color: '#F59E0B' }} />,
              },
            ].map((item, i) => (
              <Grid item xs={12} md={4} key={i}>
                <Box sx={{ textAlign: 'center', px: 2 }}>
                  <Box
                    sx={{
                      width: 64,
                      height: 64,
                      borderRadius: '50%',
                      bgcolor: 'white',
                      border: '2px solid',
                      borderColor: 'primary.main',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      mx: 'auto',
                      mb: 2,
                      boxShadow: '0 4px 20px rgba(27,122,62,0.15)',
                    }}
                  >
                    {item.icon}
                  </Box>
                  <Typography variant="overline" color="primary" fontWeight={700} sx={{ letterSpacing: 1 }}>
                    STEP {item.step}
                  </Typography>
                  <Typography variant="h6" fontWeight={700} gutterBottom>
                    {item.title}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.7 }}>
                    {item.desc}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>

          <Box sx={{ textAlign: 'center', mt: 6 }}>
            <Button
              variant="contained"
              size="large"
              startIcon={<WhatsAppIcon />}
              onClick={() => setOpenDialog(true)}
              color="primary"
              sx={{ fontWeight: 700, px: 4, py: 1.5, borderRadius: 2 }}
            >
              Get Started Free
            </Button>
          </Box>
        </Container>
      </Box>

      {/* ── COHORT 1 RESULTS ── */}
      <Box sx={{ bgcolor: 'white', py: { xs: 7, md: 10 }, borderTop: '1px solid', borderColor: 'grey.100' }}>
        <Container maxWidth="lg">
          <Typography variant="overline" color="primary" fontWeight={700} display="block" align="center" sx={{ mb: 1, letterSpacing: 2 }}>
            COHORT 1 RESULTS
          </Typography>
          <Typography variant="h3" fontWeight={800} align="center" gutterBottom sx={{ mb: 1 }}>
            Real Nigerians. Real Impact.
          </Typography>
          <Typography align="center" color="text.secondary" sx={{ mb: 6 }}>
            Our first cohort of 225 learners across 10 states — here's what they said
          </Typography>

          {/* Stats */}
          <Grid container spacing={3} sx={{ mb: 7 }}>
            {[
              { value: '225', label: 'Cohort 1 Learners', sub: 'across 10 states' },
              { value: '4.73', label: 'Average Rating', sub: 'out of 5.0 — 98% gave 4+ stars' },
              { value: '+59', label: 'NPS Score', sub: '"Excellent" — industry benchmark is 50+' },
              { value: '100%', label: 'Tried AI Tools', sub: 'every learner used at least one AI tool' },
            ].map((s, i) => (
              <Grid item xs={6} md={3} key={i}>
                <Box
                  sx={{
                    textAlign: 'center',
                    p: 3,
                    borderRadius: 3,
                    border: '1.5px solid',
                    borderColor: 'grey.100',
                    height: '100%',
                  }}
                >
                  <Typography
                    variant="h3"
                    fontWeight={800}
                    color="primary.main"
                    sx={{ lineHeight: 1, mb: 0.5, fontSize: { xs: '2rem', md: '2.5rem' } }}
                  >
                    {s.value}
                  </Typography>
                  <Typography variant="subtitle2" fontWeight={700} gutterBottom>
                    {s.label}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ lineHeight: 1.4 }}>
                    {s.sub}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>

          {/* Quotes */}
          <Grid container spacing={3}>
            {[
              {
                quote: 'I liked how AI was explained in a simple and easy way. The WhatsApp format made learning convenient and interesting.',
                name: 'Victor Solomon',
                role: 'Tech Worker, Ogun State',
              },
              {
                quote: 'I will use AI to plan my busy schedule as a surgeon and advertise my services in a more impactful way.',
                name: 'Dr Doherty Alaba',
                role: 'Surgeon, Lagos',
              },
              {
                quote: 'The fact that we were taught in Pidgin English enabled more people to understand and relate with the programme.',
                name: 'Temitope Olusanya',
                role: 'Tech Worker, Lagos',
              },
              {
                quote: 'I will use Otter.ai in all my meetings so I don\'t lose any detail, ChatGPT for my write-ups, and Canva AI for my designs.',
                name: 'Adaobi Uzoigwe',
                role: 'Business Owner, Lagos',
              },
            ].map((q, i) => (
              <Grid item xs={12} sm={6} key={i}>
                <Box
                  sx={{
                    p: 3,
                    borderRadius: 3,
                    bgcolor: 'grey.50',
                    borderLeft: '4px solid',
                    borderColor: 'primary.main',
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <Typography
                    variant="body1"
                    sx={{ fontStyle: 'italic', lineHeight: 1.7, color: 'text.primary', mb: 2, fontSize: '0.95rem' }}
                  >
                    "{q.quote}"
                  </Typography>
                  <Box>
                    <Typography variant="subtitle2" fontWeight={700} color="primary.main">
                      {q.name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {q.role}
                    </Typography>
                  </Box>
                </Box>
              </Grid>
            ))}
          </Grid>

          <Box
            sx={{
              mt: 5,
              p: 2.5,
              borderRadius: 2,
              bgcolor: '#e8f5e9',
              border: '1px solid #a5d6a7',
              textAlign: 'center',
            }}
          >
            <Typography variant="body2" color="#1b5e20" fontWeight={500}>
              83% of Cohort 1 learners measurably improved their AI literacy in just 7 days · 97.5% said they want more · Cohort 2 is open now
            </Typography>
          </Box>
        </Container>
      </Box>

      {/* ── 7-DAY JOURNEY ── */}
      <Box sx={{ bgcolor: 'white', py: { xs: 7, md: 10 } }}>
        <Container maxWidth="lg">
          <Typography variant="overline" color="primary" fontWeight={700} display="block" align="center" sx={{ mb: 1, letterSpacing: 2 }}>
            THE CURRICULUM
          </Typography>
          <Typography variant="h3" fontWeight={800} align="center" gutterBottom sx={{ mb: 1 }}>
            Your 7-Day Journey
          </Typography>
          <Typography align="center" color="text.secondary" sx={{ mb: 6 }}>
            Each day builds on the last — 5 lessons, one quiz, real skills
          </Typography>

          <Grid container spacing={2}>
            {DAYS.map((d) => (
              <Grid item xs={12} sm={6} md={4} key={d.day} sx={{ display: d.day === 7 ? { sm: 'flex' } : 'block' }}>
                <Card
                  elevation={0}
                  sx={{
                    border: '1.5px solid',
                    borderColor: 'grey.100',
                    borderRadius: 3,
                    height: '100%',
                    transition: 'all 0.2s',
                    '&:hover': { borderColor: 'primary.main', boxShadow: '0 8px 30px rgba(27,122,62,0.12)', transform: 'translateY(-2px)' },
                    ...(d.day === 7 && { borderColor: '#F59E0B', background: 'linear-gradient(135deg, #fffbeb, #fff)' }),
                  }}
                >
                  <CardContent sx={{ p: 3 }}>
                    <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 2 }}>
                      <Box
                        sx={{
                          width: 40,
                          height: 40,
                          borderRadius: 2,
                          bgcolor: d.day === 7 ? '#F59E0B' : 'primary.main',
                          color: 'white',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontWeight: 800,
                          fontSize: '0.9rem',
                          flexShrink: 0,
                        }}
                      >
                        {d.day}
                      </Box>
                      <Typography variant="h6" fontWeight={700} sx={{ fontSize: '1rem' }}>
                        {d.title}
                      </Typography>
                    </Stack>
                    <Stack spacing={0.6}>
                      {d.topics.map((t, i) => (
                        <Stack key={i} direction="row" spacing={1} alignItems="center">
                          <CheckIcon sx={{ fontSize: 14, color: d.day === 7 ? '#F59E0B' : 'primary.main', flexShrink: 0 }} />
                          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.82rem' }}>
                            {t}
                          </Typography>
                        </Stack>
                      ))}
                    </Stack>
                  </CardContent>
                </Card>
              </Grid>
            ))}

            {/* placeholder 7th-slot filler on md so grid stays even */}
            <Grid item md={4} sx={{ display: { xs: 'none', sm: 'none', md: 'block' } }} />
          </Grid>
        </Container>
      </Box>

      {/* ── LANGUAGES ── */}
      <Box
        sx={{
          background: 'linear-gradient(135deg, #1a5c2a 0%, #1B7A3E 100%)',
          py: { xs: 7, md: 9 },
          color: 'white',
        }}
      >
        <Container maxWidth="md">
          <Typography variant="overline" fontWeight={700} display="block" align="center" sx={{ mb: 1, letterSpacing: 2, opacity: 0.75 }}>
            YOUR LANGUAGE
          </Typography>
          <Typography variant="h3" fontWeight={800} align="center" gutterBottom sx={{ mb: 1 }}>
            Learn in 5 Nigerian Languages
          </Typography>
          <Typography align="center" sx={{ opacity: 0.8, mb: 5 }}>
            Education hits different in your mother tongue
          </Typography>

          <Stack
            direction="row"
            flexWrap="wrap"
            justifyContent="center"
            gap={2}
          >
            {LANGUAGES.map((lang) => (
              <Box
                key={lang.code}
                sx={{
                  px: 3,
                  py: 1.5,
                  borderRadius: 3,
                  bgcolor: 'rgba(255,255,255,0.12)',
                  border: '1px solid rgba(255,255,255,0.2)',
                  textAlign: 'center',
                  minWidth: 110,
                  backdropFilter: 'blur(4px)',
                }}
              >
                <Typography fontWeight={700} sx={{ fontSize: '1.1rem' }}>
                  {lang.native}
                </Typography>
                {lang.native !== lang.name && (
                  <Typography sx={{ opacity: 0.65, fontSize: '0.75rem' }}>
                    {lang.name}
                  </Typography>
                )}
              </Box>
            ))}
          </Stack>
        </Container>
      </Box>

      {/* ── WHY MNAIR ── */}
      <Box sx={{ bgcolor: 'grey.50', py: { xs: 7, md: 10 } }}>
        <Container maxWidth="lg">
          <Typography variant="overline" color="primary" fontWeight={700} display="block" align="center" sx={{ mb: 1, letterSpacing: 2 }}>
            WHY MNAIR
          </Typography>
          <Typography variant="h3" fontWeight={800} align="center" gutterBottom sx={{ mb: 6 }}>
            Built for Every Nigerian
          </Typography>

          <Grid container spacing={4}>
            {[
              {
                emoji: '📱',
                title: 'Works on Any Phone',
                desc: 'No smartphone needed. Our WhatsApp bot runs on basic Android and feature phones. No app download, no account creation.',
              },
              {
                emoji: '⚡',
                title: 'Zero Data Cost',
                desc: 'WhatsApp data is free on most Nigerian networks. Learn all 7 days without spending a kobo on data.',
              },
              {
                emoji: '🎓',
                title: 'Verifiable Certificate',
                desc: 'Your completion certificate has a unique ID that employers can verify online at mnair.ng/verify.',
              },
              {
                emoji: '🕐',
                title: '10 Minutes a Day',
                desc: 'Designed around Nigerian schedules. Each lesson takes 10 minutes. Do it on your commute, at lunch, whenever.',
              },
              {
                emoji: '🧠',
                title: 'Learn by Doing',
                desc: 'Every lesson ends with an interactive quiz. You need 60% to pass — and you get 3 attempts. No pressure.',
              },
              {
                emoji: '🔒',
                title: 'Your Data is Safe',
                desc: 'We comply with the Nigeria Data Protection Act (NDPA). We never sell your data or send spam.',
              },
            ].map((item, i) => (
              <Grid item xs={12} sm={6} md={4} key={i}>
                <Stack direction="row" spacing={2} alignItems="flex-start">
                  <Box sx={{ fontSize: '2rem', flexShrink: 0, mt: 0.3 }}>{item.emoji}</Box>
                  <Box>
                    <Typography variant="h6" fontWeight={700} gutterBottom sx={{ fontSize: '1rem' }}>
                      {item.title}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.7 }}>
                      {item.desc}
                    </Typography>
                  </Box>
                </Stack>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* ── BOTTOM CTA ── */}
      <Box
        sx={{
          bgcolor: 'white',
          py: { xs: 8, md: 12 },
          textAlign: 'center',
          borderTop: '1px solid',
          borderColor: 'grey.100',
        }}
      >
        <Container maxWidth="sm">
          <Typography variant="h3" fontWeight={800} gutterBottom sx={{ mb: 1 }}>
            Ready to become AI-literate?
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 4, fontSize: '1.05rem' }}>
            Join Nigerians already learning. It's free, it's on WhatsApp, and it takes just 7 days.
          </Typography>
          <Button
            variant="contained"
            size="large"
            startIcon={<WhatsAppIcon />}
            endIcon={<ArrowIcon />}
            onClick={() => setOpenDialog(true)}
            sx={{
              bgcolor: '#25D366',
              color: 'white',
              fontWeight: 700,
              fontSize: '1.1rem',
              px: 5,
              py: 1.8,
              borderRadius: 2,
              '&:hover': { bgcolor: '#1ebe57' },
              boxShadow: '0 8px 30px rgba(37,211,102,0.35)',
            }}
          >
            Start Learning Free
          </Button>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 2 }}>
            No signup · No app download · No cost
          </Typography>
        </Container>
      </Box>

      {/* ── DIALOG ── */}
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          <Typography variant="h5" fontWeight="bold">How to Start Learning</Typography>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Choose your preferred method to begin your AI literacy journey:
          </Typography>

          <Stack spacing={3}>
            {/* WhatsApp */}
            <Card variant="outlined" sx={{ borderColor: '#25D366', borderWidth: 2 }}>
              <CardContent>
                <Stack direction="row" spacing={2} alignItems="flex-start">
                  <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: '#25D366', color: 'white' }}>
                    <WhatsAppIcon />
                  </Box>
                  <Box flex={1}>
                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                      <Typography variant="h6">WhatsApp</Typography>
                      <Chip label="Available Now" size="small" color="success" />
                    </Stack>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Send <strong>"START"</strong> to:
                    </Typography>
                    <Tooltip title="Click to open WhatsApp" placement="top">
                      <Link href={WHATSAPP_LINK} target="_blank" rel="noopener noreferrer" underline="none">
                        <Typography
                          variant="h6"
                          color="primary"
                          sx={{
                            p: 1,
                            bgcolor: 'grey.100',
                            borderRadius: 1,
                            fontFamily: 'monospace',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 1,
                            '&:hover': { bgcolor: 'grey.200' },
                          }}
                        >
                          <WhatsAppIcon fontSize="small" sx={{ color: '#25D366' }} />
                          {WHATSAPP_NUMBER}
                        </Typography>
                      </Link>
                    </Tooltip>
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                      Tap to open WhatsApp with "START" pre-filled
                    </Typography>
                  </Box>
                </Stack>
              </CardContent>
            </Card>

            {/* USSD */}
            <Card variant="outlined">
              <CardContent>
                <Stack direction="row" spacing={2} alignItems="flex-start">
                  <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: 'primary.main', color: 'white' }}>
                    <DialpadIcon />
                  </Box>
                  <Box flex={1}>
                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                      <Typography variant="h6">USSD (No Internet)</Typography>
                      <Chip label="Coming Soon" size="small" color="warning" />
                    </Stack>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>Dial this code on your phone:</Typography>
                    <Typography variant="h6" color="primary" sx={{ p: 1, bgcolor: 'grey.100', borderRadius: 1, fontFamily: 'monospace' }}>
                      *384*8080#
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>Works on all Nigerian networks</Typography>
                  </Box>
                </Stack>
              </CardContent>
            </Card>

            {/* SMS */}
            <Card variant="outlined">
              <CardContent>
                <Stack direction="row" spacing={2} alignItems="flex-start">
                  <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: 'info.main', color: 'white' }}>
                    <MessageIcon />
                  </Box>
                  <Box flex={1}>
                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                      <Typography variant="h6">SMS</Typography>
                      <Chip label="Coming Soon" size="small" color="warning" />
                    </Stack>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>Send <strong>"START"</strong> to:</Typography>
                    <Typography variant="h6" color="primary" sx={{ p: 1, bgcolor: 'grey.100', borderRadius: 1, fontFamily: 'monospace' }}>
                      38480
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>Standard SMS rates may apply</Typography>
                  </Box>
                </Stack>
              </CardContent>
            </Card>
          </Stack>

          <Divider sx={{ my: 3 }} />
          <Typography variant="body2" color="text.secondary" align="center">
            After connecting, follow the prompts to select your language and start Day 1!
          </Typography>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={() => setOpenDialog(false)} variant="contained" fullWidth>Got It</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default Home
