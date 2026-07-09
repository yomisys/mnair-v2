import React, { useState, useEffect, useCallback } from 'react'
import {
  Box,
  Button,
  Card,
  CardContent,
  Container,
  TextField,
  Typography,
  Alert,
  CircularProgress,
  Grid,
  Divider,
  Chip,
} from '@mui/material'
import {
  CheckCircle as CheckIcon,
  Cancel as CancelIcon,
  Search as SearchIcon,
} from '@mui/icons-material'
import { certificatesAPI } from '../services/api'
import { format } from 'date-fns'

// Matches the backend's CertificateVerification schema exactly. The public
// endpoint deliberately never returns a name or phone number — the caller
// must already know the name (they typed it in to verify), so it's only
// ever echoed back from local state, never from the API response.
interface CertificateData {
  valid: boolean
  certificate_id: string
  issued_date: string
  language: string
  average_score: number
  completion_grade: string
}

const VerifyCertificate: React.FC = () => {
  const [certificateId, setCertificateId] = useState('')
  const [name, setName] = useState('')
  const [certificate, setCertificate] = useState<CertificateData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)

  const runVerify = useCallback(async (id: string, holderName: string) => {
    setError(null)
    setCertificate(null)
    setHasSearched(true)
    setIsLoading(true)

    try {
      const data = await certificatesAPI.verifyCertificate(id.trim(), holderName.trim())
      setCertificate(data)
    } catch (err: any) {
      if (err.response?.status === 404) {
        // Deliberately vague: an unknown code and a name that doesn't
        // match the real code both return the same message, so this page
        // can't be used to check whether a code exists at all.
        setError("No certificate found with that ID and name together. Double-check both and try again.")
      } else {
        setError(err.response?.data?.detail || 'Failed to verify certificate. Please try again.')
      }
    } finally {
      setIsLoading(false)
    }
  }, [])

  // The learner's own certificate-ready notification carries ?code=...&name=...
  // (their own data, sent to their own phone) so they land here pre-filled
  // instead of an empty form. A stranger sharing just the code has no name
  // to append, so this auto-fill never helps anyone but the actual holder.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const prefilledName = params.get('name')
    if (code && prefilledName) {
      setCertificateId(code)
      setName(prefilledName)
      runVerify(code, prefilledName)
    } else if (code) {
      setCertificateId(code)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    await runVerify(certificateId, name)
  }

  return (
    <Box sx={{ bgcolor: 'grey.50', minHeight: '100vh', py: 8 }}>
      <Container maxWidth="md">
        {/* Header */}
        <Box sx={{ textAlign: 'center', mb: 6 }}>
          <Typography variant="h3" gutterBottom fontWeight="bold">
            Verify Certificate
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Enter the certificate ID and the name printed on it to verify authenticity
          </Typography>
        </Box>

        {/* Search Form */}
        <Card sx={{ mb: 4 }}>
          <CardContent sx={{ p: 4 }}>
            <form onSubmit={handleVerify}>
              <TextField
                label="Certificate ID"
                fullWidth
                value={certificateId}
                onChange={(e) => setCertificateId(e.target.value)}
                placeholder="MNAIR-2024-00123-A7B9C2"
                required
                disabled={isLoading}
                sx={{ mb: 3 }}
                helperText="Format: MNAIR-YEAR-USERID-RANDOM"
              />

              <TextField
                label="Full Name"
                fullWidth
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Name as printed on the certificate"
                required
                disabled={isLoading}
                sx={{ mb: 3 }}
                helperText="Must match the name on the certificate exactly"
              />

              <Button
                type="submit"
                variant="contained"
                fullWidth
                size="large"
                disabled={isLoading || !certificateId.trim() || !name.trim()}
                startIcon={isLoading ? <CircularProgress size={20} color="inherit" /> : <SearchIcon />}
              >
                {isLoading ? 'Verifying...' : 'Verify Certificate'}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Error Message */}
        {error && (
          <Alert severity="error" icon={<CancelIcon />} sx={{ mb: 4 }}>
            {error}
          </Alert>
        )}

        {/* Certificate Details */}
        {certificate && (
          <Card>
            <CardContent sx={{ p: 4 }}>
              {/* Valid Badge */}
              <Box sx={{ display: 'flex', justifyContent: 'center', mb: 3 }}>
                <Chip
                  icon={<CheckIcon />}
                  label="Valid Certificate"
                  color="success"
                  size="medium"
                  sx={{ px: 2, py: 3, fontSize: '1rem' }}
                />
              </Box>

              <Typography variant="h5" align="center" gutterBottom fontWeight="bold" color="primary">
                {name}
              </Typography>

              <Typography variant="body2" align="center" color="text.secondary" sx={{ mb: 4 }}>
                Successfully completed the MNAIR AI Literacy Program
              </Typography>

              <Divider sx={{ my: 3 }} />

              {/* Certificate Details Grid */}
              <Grid container spacing={3}>
                <Grid item xs={12} sm={6}>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Certificate ID
                  </Typography>
                  <Typography variant="body1" fontWeight="medium">
                    {certificate.certificate_id}
                  </Typography>
                </Grid>

                <Grid item xs={12} sm={6}>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Completion Date
                  </Typography>
                  <Typography variant="body1" fontWeight="medium">
                    {format(new Date(certificate.issued_date), 'MMMM d, yyyy')}
                  </Typography>
                </Grid>

                <Grid item xs={12} sm={6}>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Quiz Average
                  </Typography>
                  <Typography variant="body1" fontWeight="medium" color="success.main">
                    {certificate.average_score.toFixed(1)}%
                  </Typography>
                </Grid>

                <Grid item xs={12} sm={6}>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Language
                  </Typography>
                  <Typography variant="body1" fontWeight="medium" sx={{ textTransform: 'capitalize' }}>
                    {certificate.language}
                  </Typography>
                </Grid>

                <Grid item xs={12} sm={6}>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Grade
                  </Typography>
                  <Typography variant="body1" fontWeight="medium">
                    {certificate.completion_grade}
                  </Typography>
                </Grid>
              </Grid>

              <Divider sx={{ my: 3 }} />

              <Alert severity="info" sx={{ mt: 3 }}>
                This certificate was issued by the Make Nigeria AI Ready (MNAIR) platform. The
                holder has successfully completed a 7-day AI literacy program covering fundamental
                AI concepts, applications, and ethics.
              </Alert>
            </CardContent>
          </Card>
        )}

        {/* No Results */}
        {!certificate && !error && hasSearched && !isLoading && (
          <Alert severity="info">
            No certificate found with this ID. Please verify the certificate ID and try again.
          </Alert>
        )}

        {/* Help Section */}
        <Box sx={{ mt: 6, textAlign: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            Certificate IDs can be found on the certificate document
          </Typography>
          <Typography variant="body2" color="text.secondary">
            For assistance, contact info@mnair.ng
          </Typography>
        </Box>
      </Container>
    </Box>
  )
}

export default VerifyCertificate
