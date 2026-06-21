/** Official knockout venues — keep in sync with data/seed/knockout_fixtures.csv */
export const KNOCKOUT_HOST_COUNTRY: Record<number, string> = {
  73: 'US', 74: 'US', 75: 'MX', 76: 'US', 77: 'US', 78: 'US', 79: 'MX', 80: 'US',
  81: 'US', 82: 'US', 83: 'CA', 84: 'US', 85: 'CA', 86: 'US', 87: 'US', 88: 'US',
  89: 'US', 90: 'US', 91: 'US', 92: 'MX', 93: 'US', 94: 'US', 95: 'US', 96: 'CA',
  97: 'US', 98: 'US', 99: 'US', 100: 'US', 101: 'US', 102: 'US', 103: 'US', 104: 'US',
}

const CO_HOST = new Set(['MX', 'US', 'CA'])

export function venueHomeBoost(countryCode: string, matchNumber: number): boolean {
  const hostCountry = KNOCKOUT_HOST_COUNTRY[matchNumber]
  return !!hostCountry && CO_HOST.has(hostCountry) && countryCode === hostCountry
}
