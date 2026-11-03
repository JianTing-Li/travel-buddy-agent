/** Loading errors without assuming a slow or unreachable server is asleep. Owner: Jian. */
import { ApiError, OFFLINE, TIMED_OUT } from '../../app/httpApi.ts'

export function loadProblem(error: unknown): string {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    return 'Check your connection, then try again.'
  }
  if (error instanceof ApiError && (error.status === OFFLINE || error.status === TIMED_OUT)) {
    return 'The server did not respond. It may still be waking up. Please try again.'
  }
  return 'Something went wrong on our side. Try again in a moment.'
}
