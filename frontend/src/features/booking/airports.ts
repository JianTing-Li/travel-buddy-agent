/** City names for the airports in the test data, so cards read "New York to Los Angeles" and not only "JFK to LAX". Owner: Jian. */
const CITIES: Record<string, string> = {
  JFK: 'New York',
  LAX: 'Los Angeles',
  ORD: 'Chicago',
  DEN: 'Denver',
  BOS: 'Boston',
  MIA: 'Miami',
  SEA: 'Seattle',
  SFO: 'San Francisco',
  LHR: 'London Heathrow',
  LTN: 'London Luton',
  LGW: 'London Gatwick',
  STN: 'London Stansted',
  DXB: 'Dubai',
}

/** The city for an airport code, or the code itself when it is not in the table. */
export function cityName(code: string): string {
  return CITIES[code] ?? code
}
