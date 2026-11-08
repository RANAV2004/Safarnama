// small map of one place from OpenStreetMap
export default function MapView({ lat, lng, name }: { lat: number; lng: number; name: string }) {
  const d = 0.012;
  const bbox = [lng - d, lat - d * 0.7, lng + d, lat + d * 0.7].map((n) => n.toFixed(4)).join(",");
  const src = `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${lat.toFixed(5)},${lng.toFixed(5)}`;
  return (
    <div className="map">
      <iframe title={`Map of ${name}`} src={src} loading="lazy" referrerPolicy="no-referrer" />
      <p className="map-credit muted small">
        Map ©{" "}
        <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
          OpenStreetMap
        </a>{" "}
        contributors
      </p>
    </div>
  );
}
