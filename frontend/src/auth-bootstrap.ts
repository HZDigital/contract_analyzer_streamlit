/** Reuses a silent-auth request across React Strict Mode effect remounts. */
export function getOrStartSsoAttempt<T>(
  attempt: { current: Promise<T> | undefined },
  start: () => Promise<T>,
): Promise<T> {
  if (!attempt.current) {
    attempt.current = start();
  }
  return attempt.current;
}
