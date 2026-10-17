import React from 'react'
import { alpha, Avatar, Box, Button, Paper, Stack, Typography } from '@mui/material'
import { createTheme, Theme } from '@mui/material/styles'
import { OpenInNew as OpenIcon } from '@mui/icons-material'
import { assetUrl, SponsorAdvert } from '../services/api'

/**
 * White-label building blocks shared by the sponsor landing page (/s/<code>),
 * the sponsor portal and /learn: a theme in the sponsor's colour, the
 * sponsor's mark, and its advert card.
 */

export const DEFAULT_BRAND = '#008751'

const luminance = (hex: string): number => {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** Black or white, whichever reads better on the sponsor's colour. */
export const textOn = (hex: string): string => (luminance(hex) > 0.45 ? '#111111' : '#FFFFFF')

export const brandTheme = (base: Theme, color: string | null | undefined): Theme => {
  const main = color && /^#[0-9A-Fa-f]{6}$/.test(color) ? color : DEFAULT_BRAND
  return createTheme(base, {
    palette: { primary: base.palette.augmentColor({ color: { main, contrastText: textOn(main) } }) },
  })
}

export const BrandMark: React.FC<{ name: string; logoUrl: string | null; size?: number; light?: boolean }> = ({
  name, logoUrl, size = 40, light,
}) => {
  const src = assetUrl(logoUrl)
  if (src) {
    return (
      <Box
        component="img"
        src={src}
        alt={`${name} logo`}
        sx={{
          height: size, maxWidth: size * 3.5, objectFit: 'contain', display: 'block',
          ...(light && { bgcolor: 'white', borderRadius: 1.5, p: 0.5 }),
        }}
      />
    )
  }
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase()
  return (
    <Avatar
      sx={{
        width: size, height: size, fontWeight: 800, fontSize: size * 0.4,
        bgcolor: light ? 'white' : 'primary.main', color: light ? 'primary.main' : 'primary.contrastText',
      }}
    >
      {initials}
    </Avatar>
  )
}

/**
 * The sponsor's advert. Always labelled as sponsored so learners can tell it
 * apart from the course, and its link opens in a new tab marked
 * rel="sponsored".
 */
export const SponsorAdvertCard: React.FC<{
  advert: SponsorAdvert
  sponsorName: string
  variant?: 'feature' | 'compact'
  onDismiss?: () => void
}> = ({ advert, sponsorName, variant = 'feature', onDismiss }) => {
  const image = assetUrl(advert.image_url)
  const compact = variant === 'compact'
  return (
    <Paper
      elevation={0}
      sx={{
        overflow: 'hidden', borderRadius: compact ? 2.5 : 4, border: '1px solid',
        borderColor: (t) => alpha(t.palette.primary.main, 0.25),
        bgcolor: (t) => alpha(t.palette.primary.main, 0.04),
        display: 'flex', flexDirection: compact ? 'row' : { xs: 'column', md: 'row' },
      }}
    >
      {image && (
        <Box
          component="img"
          src={image}
          alt=""
          sx={compact
            ? { width: 88, minHeight: 88, objectFit: 'cover', flexShrink: 0 }
            : { width: { xs: '100%', md: '42%' }, maxHeight: { xs: 240, md: 'none' }, objectFit: 'cover', flexShrink: 0 }}
        />
      )}
      <Box sx={{ p: compact ? 1.5 : { xs: 3, md: 4 }, flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
          <Typography
            variant="overline"
            sx={{ color: 'primary.main', fontWeight: 800, letterSpacing: 1.2, lineHeight: 1.6, fontSize: compact ? '0.65rem' : '0.72rem' }}
          >
            Sponsored · {sponsorName}
          </Typography>
          {onDismiss && (
            <Button size="small" onClick={onDismiss} sx={{ minWidth: 0, px: 1, color: 'text.secondary', fontSize: '0.72rem' }}>
              Hide
            </Button>
          )}
        </Stack>
        <Typography
          variant={compact ? 'subtitle1' : 'h4'}
          component="p"
          sx={{ fontWeight: 800, lineHeight: 1.2, mt: compact ? 0 : 0.5, fontSize: compact ? '0.98rem' : { xs: '1.6rem', md: '2rem' } }}
        >
          {advert.headline}
        </Typography>
        {advert.body && (
          <Typography
            color="text.secondary"
            sx={{
              mt: compact ? 0.25 : 1.5, whiteSpace: 'pre-line', fontSize: compact ? '0.85rem' : '1.05rem',
              ...(compact && { display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }),
            }}
          >
            {advert.body}
          </Typography>
        )}
        {advert.cta_url && (
          <Box sx={{ mt: compact ? 1 : 3 }}>
            <Button
              variant="contained"
              size={compact ? 'small' : 'large'}
              href={advert.cta_url}
              target="_blank"
              rel="noopener noreferrer sponsored"
              endIcon={<OpenIcon fontSize="small" />}
              sx={{ fontWeight: 700, borderRadius: 99, px: compact ? 2 : 3.5, boxShadow: 'none' }}
            >
              {advert.cta_label || 'Learn more'}
            </Button>
          </Box>
        )}
      </Box>
    </Paper>
  )
}
