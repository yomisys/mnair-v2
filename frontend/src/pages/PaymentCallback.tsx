import React, { useEffect, useState } from 'react'
import { Alert, Box, Button, CircularProgress, Container, Paper, Typography } from '@mui/material'
import { CheckCircle as OkIcon } from '@mui/icons-material'
import { formatNaira, paymentsAPI, PaymentStatus } from '../services/api'

/**
 * Where Paystack sends a payer back (?reference=...&trxref=...). Asks the
 * backend to confirm with Paystack directly, so the result is right even if
 * the webhook is late. Polls briefly because bank transfers settle a few
 * seconds after the checkout closes.
 */
const PaymentCallback: React.FC = () => {
  const params = new URLSearchParams(window.location.search)
  const reference = params.get('reference') || params.get('trxref') || ''
  const [payment, setPayment] = useState<PaymentStatus | null>(null)
  const [error, setError] = useState<string | null>(reference ? null : 'No payment reference in this link.')

  useEffect(() => {
    if (!reference) return
    let cancelled = false
    let tries = 0
    const check = async () => {
      try {
        const p = await paymentsAPI.verify(reference)
        if (cancelled) return
        setPayment(p)
        if (p.status !== 'success' && tries++ < 6) window.setTimeout(check, 5000)
      } catch {
        if (!cancelled) setError('We could not check this payment right now. Refresh this page in a minute.')
      }
    }
    check()
    return () => { cancelled = true }
  }, [reference])

  const isSponsor = payment?.purpose.startsWith('sponsor')
  const done = payment?.status === 'success'

  return (
    <Container maxWidth="xs" sx={{ py: 6 }}>
      <Paper elevation={0} sx={{ p: 4, border: '1px solid', borderColor: 'grey.200', borderRadius: 3, textAlign: 'center' }}>
        {error && <Alert severity="warning">{error}</Alert>}
        {!error && !payment && (
          <Box sx={{ py: 3 }}>
            <CircularProgress />
            <Typography sx={{ mt: 2 }}>Confirming your payment…</Typography>
          </Box>
        )}
        {payment && done && (
          <>
            <OkIcon color="success" sx={{ fontSize: 56 }} />
            <Typography variant="h5" fontWeight={800} sx={{ mt: 1 }}>Payment received</Typography>
            <Typography color="text.secondary" sx={{ mt: 1, mb: 3 }}>
              {formatNaira(payment.amount_kobo)} · ref {payment.reference}
            </Typography>
            {isSponsor ? (
              <Button variant="contained" href="/sponsor" fullWidth>Back to your sponsor dashboard</Button>
            ) : (
              <>
                <Typography sx={{ mb: 2 }}>
                  Your verified certificate is unlocked. Go back to your course and tap <strong>Get certificate</strong>.
                </Typography>
                <Button variant="contained" href="/learn" fullWidth>Back to my course</Button>
              </>
            )}
          </>
        )}
        {payment && !done && (
          <>
            <Typography variant="h6" fontWeight={800}>
              {payment.status === 'failed' ? 'Payment failed' : 'Payment not confirmed yet'}
            </Typography>
            <Typography color="text.secondary" sx={{ mt: 1, mb: 3 }}>
              {payment.status === 'failed'
                ? 'No money was taken. You can try again.'
                : 'Bank transfers and USSD can take a few minutes. This page checks again automatically.'}
            </Typography>
            <Button variant="outlined" href={isSponsor ? '/sponsor' : '/learn'} fullWidth>
              {isSponsor ? 'Back to dashboard' : 'Back to my course'}
            </Button>
          </>
        )}
      </Paper>
    </Container>
  )
}

export default PaymentCallback
