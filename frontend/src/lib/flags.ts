/** Map FIFA 3-letter codes to flag emoji (ISO 3166-1 alpha-2 regional indicators). */
const FIFA_TO_ISO: Record<string, string> = {
  MEX: 'MX', RSA: 'ZA', KOR: 'KR', CZE: 'CZ', CAN: 'CA', SUI: 'CH', QAT: 'QA', BIH: 'BA',
  BRA: 'BR', MAR: 'MA', HAI: 'HT', USA: 'US', PAR: 'PY', AUS: 'AU', TUR: 'TR', GER: 'DE',
  CUW: 'CW', CIV: 'CI', ECU: 'EC', NED: 'NL', JPN: 'JP', TUN: 'TN', SWE: 'SE', BEL: 'BE',
  EGY: 'EG', IRN: 'IR', NZL: 'NZ', ESP: 'ES', CPV: 'CV', KSA: 'SA', URU: 'UY', FRA: 'FR',
  SEN: 'SN', NOR: 'NO', IRQ: 'IQ', ARG: 'AR', ALG: 'DZ', AUT: 'AT', JOR: 'JO', POR: 'PT',
  UZB: 'UZ', COL: 'CO', COD: 'CD', CRO: 'HR', GHA: 'GH', PAN: 'PA',
}

/** Subdivision flags where ISO alpha-2 is ambiguous (ENG/SCO use UK tag sequences). */
const FIFA_FLAG_EMOJI: Record<string, string> = {
  ENG: '\u{1F3F4}\u{E0067}\u{E0062}\u{E0065}\u{E006E}\u{E0067}\u{E007F}',
  SCO: '\u{1F3F4}\u{E0067}\u{E0062}\u{E0073}\u{E0063}\u{E0074}\u{E007F}',
}

function isoToEmoji(iso: string): string {
  if (iso.length !== 2) return '🏳️'
  return [...iso.toUpperCase()].map(char => String.fromCodePoint(127397 + char.charCodeAt(0))).join('')
}

export function flagEmoji(fifaCode: string): string {
  const code = fifaCode.toUpperCase()
  if (FIFA_FLAG_EMOJI[code]) return FIFA_FLAG_EMOJI[code]
  const iso = FIFA_TO_ISO[code]
  return iso ? isoToEmoji(iso) : '🏳️'
}
