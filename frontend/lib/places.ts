// city coordinates
export type Place = { name: string; lon: number; lat: number };
const COORDS: Record<string, [number, number]> = {
  Indore: [75.86, 22.72],
  Mumbai: [72.88, 19.08],
  Bengaluru: [77.59, 12.97],
  Delhi: [77.21, 28.61],
  Goa: [73.83, 15.49],
  Jaipur: [75.79, 26.91],
  Udaipur: [73.71, 24.58],
  Mysuru: [76.64, 12.3],
};

export function place(name: string): Place {
  const [lon, lat] = COORDS[name] ?? [78.96, 22.59];
  return { name, lon, lat };
}
