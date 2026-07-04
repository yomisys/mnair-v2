import React, { useState } from 'react'
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

interface CertificateData {
  certificate_id: string
  learner_name: string
  learner_phone: string
  completion_date: string
  final_score: number
  is_valid: boolean
  language: string
}

const VerifyCertificate: React.FC = () => {
  const [certificateId, setCertificateId] = useState('')
  const [certificate, setCertificate] = useState<CertificateData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setCertificate(null)
    setHasSearched(true)
    setIsLoading(true)

    try {
      const data = await certificatesAPI.verifyCertificate(certificateId.trim())
      setCertificate(data)
    } catch (err: any) {
      if (err.response?.status === 404) {
        setError('Certificate not found. Please check the ID and try again.')
      } else {
        setError(err.response?.data?.detail || 'Failed to verify certificate. Please try again.')
      }
    } finally {
      setIsLoading(false)
    }
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
            Enter a certificate ID to verify its authenticity
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

              <Button
                type="submit"
                variant="contained"
                fullWidth
                size="large"
                disabled={isLoading || !certificateId.trim()}
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
                {certificate.learner_name}
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
                    {format(new Date(certificate.completion_date), 'MMMM d, yyyy')}
                  </Typography>
                </Grid>

                <Grid item xs={12} sm={6}>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Final Score
                  </Typography>
                  <Typography variant="body1" fontWeight="medium" color="success.main">
                    {certificate.final_score.toFixed(1)}%
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
                    Phone Number
                  </Typography>
                  <Typography variant="body1" fontWeight="medium">
                    {certificate.learner_phone}
                  </Typography>
                </Grid>

                <Grid item xs={12} sm={6}>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Status
                  </Typography>
                  <Chip
                    label={certificate.is_valid ? 'Valid' : 'Invalid'}
                    color={certificate.is_valid ? 'success' : 'error'}
                    size="small"
                  />
                </Grid>
              </Grid>

              <Divider sx={{ my: 3 }} />

              <Alert severity="info" sx={{ mt: 3 }}>
                This certificate was issued by the Make Nigeria AI Ready (MNAIR) platform and is
                officially recognized. The holder has successfully completed a 7-day AI literacy
                program covering fundamental AI concepts, applications, and ethics.
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
