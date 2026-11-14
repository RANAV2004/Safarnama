// map of one place from Google Maps, by position when we know it, otherwise by name
export default function MapView({
  lat,
  lng,
  query,
  name,
}: {
  lat?: number | null;
  lng?: number | null;
  query: string;
  name: string;
}) {
  const where = lat != null && lng != null ? `${lat.toFixed(6)},${lng.toFixed(6)}` : query;
  const src = `https://maps.google.com/maps?q=${encodeURIComponent(where)}&z=15&hl=en&output=embed`;
  return (
    <div className="map">
      <iframe
        title={`Map of ${name}`}
        src={src}
        loading="lazy"
        referrerPolicy="no-referrer-when-downgrade"
        allowFullScreen
      />
    </div>
  );
}
