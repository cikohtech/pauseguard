import { ApiError } from '@/lib/api'

/** The i18n key of the message to show the customer for a failed call (never raw API text). */
export function errorKey(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return 'customer.errors.network'
    if (err.status === 429) return 'customer.errors.rateLimited'
  }
  return 'customer.errors.generic'
}
