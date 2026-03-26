import React from 'react'
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
} from '@mui/material'
import {
  School as SchoolIcon,
  Phone as PhoneIcon,
  Language as LanguageIcon,
  EmojiEvents as TrophyIcon,
  Speed as SpeedIcon,
  Public as PublicIcon,
} from '@mui/icons-material'

const FeatureCard: React.FC<{
  icon: React.ReactElement
  title: string
  description: string
}> = ({ icon, title, description }) => (
  <Card sx={{ height: '100%', textAlign: 'center' }}>
    <CardContent sx={{ p: 3 }}>
      <Box
        sx={{
          display: 'inline-flex',
          p: 2,
          borderRadius: 2,
          bgcolor: 'primary.main',
          color: 'white',
          mb: 2,
        }}
      >
        {icon}
      </Box>
      <Typography variant="h6" gutterBottom>
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {description}
      </Typography>
    </CardContent>
  </Card>
)

const Home: React.FC = () => {
  const navigate = useNavigate()

  return (
    <Box>
      {/* Hero Section */}
      <Box
        sx={{
          bgcolor: 'primary.main',
          color: 'white',
          py: { xs: 8, md: 12 },
          textAlign: 'center',
        }}
      >
        <Container maxWidth="md">
          <Typography
            variant="h2"
            component="h1"
            gutterBottom
            fontWeight="bold"
            sx={{ fontSize: { xs: '2rem', md: '3.5rem' } }}
          >
            Make Nigeria AI Ready
          </Typography>
          <Typography variant="h5" sx={{ mb: 4, opacity: 0.9 }}>
            Free 7-day AI literacy program for all Nigerians
          </Typography>
          <Typography variant="body1" sx={{ mb: 4, fontSize: '1.1rem' }}>
            Learn about Artificial Intelligence in your language. No data charges. No prerequisites.
            Earn a certificate on completion.
          </Typography>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={2}
            justifyContent="center"
          >
            <Button
              variant="contained"
              size="large"
              sx={{
                bgcolor: 'white',
                color: 'primary.main',
                '&:hover': { bgcolor: 'grey.100' },
                px: 4,
                py: 1.5,
              }}
            >
              Start Learning (WhatsApp)
            </Button>
            <Button
              variant="outlined"
              size="large"
              onClick={() => navigate('/verify')}
              sx={{
                borderColor: 'white',
                color: 'white',
                '&:hover': { borderColor: 'white', bgcolor: 'rgba(255,255,255,0.1)' },
                px: 4,
                py: 1.5,
              }}
            >
              Verify Certificate
            </Button>
          </Stack>
        </Container>
      </Box>

      {/* Features Section */}
      <Container maxWidth="lg" sx={{ py: 8 }}>
        <Typography variant="h3" align="center" gutterBottom fontWeight="bold">
          Why MNAIR?
        </Typography>
        <Typography
          variant="body1"
          align="center"
          color="text.secondary"
          sx={{ mb: 6, maxWidth: 600, mx: 'auto' }}
        >
          Empowering millions of Nigerians with AI knowledge through accessible,
          localized education
        </Typography>

        <Grid container spacing={4}>
          <Grid item xs={12} md={4}>
            <FeatureCard
              icon={<LanguageIcon fontSize="large" />}
              title="5 Nigerian Languages"
              description="Learn in English, Pidgin, Hausa, Yoruba, or Igbo. Education in your mother tongue."
            />
          </Grid>
          <Grid item xs={12} md={4}>
            <FeatureCard
              icon={<PhoneIcon fontSize="large" />}
              title="Multiple Channels"
              description="Access via WhatsApp, USSD (*384*8080#), or SMS. Works on any phone."
            />
          </Grid>
          <Grid item xs={12} md={4}>
            <FeatureCard
              icon={<SpeedIcon fontSize="large" />}
              title="Just 7 Days"
              description="Complete the program in one week. 5 topics per day, 10 minutes each."
            />
          </Grid>
          <Grid item xs={12} md={4}>
            <FeatureCard
              icon={<SchoolIcon fontSize="large" />}
              title="Learn by Doing"
              description="Interactive quizzes after each lesson. Pass rate: 60%. Up to 3 attempts."
            />
          </Grid>
          <Grid item xs={12} md={4}>
            <FeatureCard
              icon={<TrophyIcon fontSize="large" />}
              title="Earn Certificate"
              description="Get a verifiable certificate upon completion. Recognized by employers."
            />
          </Grid>
          <Grid item xs={12} md={4}>
            <FeatureCard
              icon={<PublicIcon fontSize="large" />}
              title="100% Free"
              description="No hidden costs. No data charges. Proudly supported by the Federal Government."
            />
          </Grid>
        </Grid>
      </Container>

      {/* Curriculum Overview */}
      <Box sx={{ bgcolor: 'grey.50', py: 8 }}>
        <Container maxWidth="lg">
          <Typography variant="h3" align="center" gutterBottom fontWeight="bold">
            7-Day Curriculum
          </Typography>
          <Typography
            variant="body1"
            align="center"
            color="text.secondary"
            sx={{ mb: 6 }}
          >
            Each day covers 5 essential AI topics
          </Typography>

          <Grid container spacing={3}>
            {[
              {
                day: 'Day 1-7',
                topics: [
                  'What is AI?',
                  'How AI Works',
                  'AI in Nigeria',
                  'AI Tools You Can Use',
                  'AI Ethics & Safety',
                ],
              },
            ].map((item, idx) => (
              <Grid item xs={12} key={idx}>
                <Card>
                  <CardContent sx={{ p: 3 }}>
                    <Typography variant="h6" color="primary" gutterBottom>
                      {item.day}
                    </Typography>
                    <Stack spacing={1}>
                      {item.topics.map((topic, topicIdx) => (
                        <Typography key={topicIdx} variant="body2">
                          ✓ {topic}
                        </Typography>
                      ))}
                    </Stack>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Stats Section */}
      <Container maxWidth="lg" sx={{ py: 8 }}>
        <Grid container spacing={4} textAlign="center">
          <Grid item xs={12} md={3}>
            <Typography variant="h3" color="primary" fontWeight="bold">
              175
            </Typography>
            <Typography variant="body1" color="text.secondary">
              Lessons Available
            </Typography>
          </Grid>
          <Grid item xs={12} md={3}>
            <Typography variant="h3" color="primary" fontWeight="bold">
              5
            </Typography>
            <Typography variant="body1" color="text.secondary">
              Languages Supported
            </Typography>
          </Grid>
          <Grid item xs={12} md={3}>
            <Typography variant="h3" color="primary" fontWeight="bold">
              7
            </Typography>
            <Typography variant="body1" color="text.secondary">
              Days to Complete
            </Typography>
          </Grid>
          <Grid item xs={12} md={3}>
            <Typography variant="h3" color="primary" fontWeight="bold">
              Free
            </Typography>
            <Typography variant="body1" color="text.secondary">
              No Cost Ever
            </Typography>
          </Grid>
        </Grid>
      </Container>

      {/* CTA Section */}
      <Box
        sx={{
          bgcolor: 'primary.main',
          color: 'white',
          py: 8,
          textAlign: 'center',
        }}
      >
        <Container maxWidth="md">
          <Typography variant="h3" gutterBottom fontWeight="bold">
            Ready to Start Learning?
          </Typography>
          <Typography variant="h6" sx={{ mb: 4, opacity: 0.9 }}>
            Join thousands of Nigerians getting AI-ready
          </Typography>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={2}
            justifyContent="center"
          >
            <Button
              variant="contained"
              size="large"
              sx={{
                bgcolor: 'white',
                color: 'primary.main',
                '&:hover': { bgcolor: 'grey.100' },
                px: 4,
                py: 1.5,
              }}
            >
              Send 'START' to WhatsApp
            </Button>
            <Button
              variant="outlined"
              size="large"
              sx={{
                borderColor: 'white',
                color: 'white',
                '&:hover': { borderColor: 'white', bgcolor: 'rgba(255,255,255,0.1)' },
                px: 4,
                py: 1.5,
              }}
            >
              Dial *384*8080#
            </Button>
          </Stack>
        </Container>
      </Box>
    </Box>
  )
}

export default Home
