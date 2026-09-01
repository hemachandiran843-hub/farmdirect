/* FarmDirect — interactive SVG map mockup for Route Optimization.
   Renders a simulated city (grid roads, parks, river), the hub, delivery
   stops and the AI-optimized routes produced by the backend. No external
   map API needed — works fully offline. */

function latLngToXY(lat, lng, bounds, w, h) {
  const { minLat, maxLat, minLng, maxLng } = bounds;
  const x = ((lng - minLng) / (maxLng - minLng)) * (w - 80) + 40;
  const y = h - (((lat - minLat) / (maxLat - minLat)) * (h - 80) + 40);
  return { x, y };
}

const ROUTE_COLORS = ['#1e7d3e', '#e8a013', '#166088', '#c94f3d', '#5b3fa8'];

function renderFdMap(containerId, data) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const W = 900, H = 560;

  // ---- bounds from all points (hub + all route paths) ----
  const pts = [[data.hub.lat, data.hub.lng]];
  (data.routes || []).forEach(r => (r.path || []).forEach(p => pts.push([p.lat, p.lng])));
  (data.unassigned || []).forEach(p => pts.push([p.lat, p.lng]));
  let minLat = Math.min(...pts.map(p => p[0])), maxLat = Math.max(...pts.map(p => p[0]));
  let minLng = Math.min(...pts.map(p => p[1])), maxLng = Math.max(...pts.map(p => p[1]));
  const pad = 0.012;
  minLat -= pad; maxLat += pad; minLng -= pad; maxLng += pad;
  const bounds = { minLat, maxLat, minLng, maxLng };

  // ---- base layer: simulated city ----
  let svg = `<svg viewBox="0 0 ${W} ${H}" class="fd-map" id="fd-svg">`;
  // city blocks
  for (let i = 0; i < 9; i++) {
    for (let j = 0; j < 6; j++) {
      if ((i + j) % 4 === 3) continue;
      const x = 30 + i * (W - 60) / 9, y = 26 + j * (H - 52) / 6;
      svg += `<rect class="map-block" x="${x + 8}" y="${y + 8}" width="${(W - 60) / 9 - 26}" height="${(H - 52) / 6 - 26}" rx="7"/>`;
    }
  }
  // roads
  for (let i = 0; i <= 9; i++) {
    const x = 30 + i * (W - 60) / 9;
    svg += `<line class="${i % 3 === 0 ? 'map-road' : 'map-road-minor'}" x1="${x}" y1="20" x2="${x}" y2="${H - 20}"/>`;
  }
  for (let j = 0; j <= 6; j++) {
    const y = 26 + j * (H - 52) / 6;
    svg += `<line class="${j % 2 === 0 ? 'map-road' : 'map-road-minor'}" x1="20" y1="${y}" x2="${W - 20}" y2="${y}"/>`;
  }
  // river
  svg += `<path class="map-river" d="M -20 ${H * 0.16} C ${W * 0.25} ${H * 0.30}, ${W * 0.4} ${H * 0.02}, ${W + 30} ${H * 0.2}"/>`;
  // parks
  svg += `<rect class="map-park" x="${W * 0.62}" y="${H * 0.58}" width="130" height="90" rx="14"/>`;
  svg += `<rect class="map-park" x="${W * 0.12}" y="${H * 0.66}" width="100" height="70" rx="14"/>`;
  svg += `<text x="${W * 0.62 + 38}" y="${H * 0.58 + 50}" class="map-stop-label">Central Park</text>`;

  const hubXY = latLngToXY(data.hub.lat, data.hub.lng, bounds, W, H);

  // ---- routes ----
  (data.routes || []).forEach((route, ri) => {
    const color = ROUTE_COLORS[ri % ROUTE_COLORS.length];
    const d = (route.path || []).map(p => {
      const { x, y } = latLngToXY(p.lat, p.lng, bounds, W, H);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    svg += `<polyline class="map-route ${data.animate ? 'anim' : ''}" points="${d}" stroke="${color}" opacity="0.85"/>`;
  });

  // ---- stops ----
  (data.routes || []).forEach((route, ri) => {
    const color = ROUTE_COLORS[ri % ROUTE_COLORS.length];
    (route.stops || []).forEach((s, si) => {
      const { x, y } = latLngToXY(s.lat, s.lng, bounds, W, H);
      svg += `<g class="map-stop" data-order="${s.order_code}" data-area="${s.area}" data-buyer="${s.buyer}"
                onmouseenter="fdHighlightStop(this)" onmouseleave="fdClearHighlight()">
                <title>${route.vehicle} · Stop ${si + 1} · ${s.order_code}</title>
                <circle cx="${x}" cy="${y}" r="13" fill="#fff" stroke="${color}" stroke-width="3"/>
                <text x="${x}" y="${y + 4}" text-anchor="middle" font-size="10" font-weight="800" fill="${color}">${si + 1}</text>
              </g>`;
    });
  });

  // ---- unassigned markers (gray) ----
  (data.unassigned || []).forEach(p => {
    const { x, y } = latLngToXY(p.lat, p.lng, bounds, W, H);
    svg += `<g><circle cx="${x}" cy="${y}" r="9" fill="#9aa8a0" opacity="0.85"/>
            <title>${p.order_code} — inter-city / not in city pool</title></g>`;
  });

  // ---- hub ----
  svg += `<g>
    <circle cx="${hubXY.x}" cy="${hubXY.y}" r="20" fill="#1c2b22" opacity="0.12"/>
    <circle cx="${hubXY.x}" cy="${hubXY.y}" r="14" fill="#1c2b22"/>
    <text x="${hubXY.x}" y="${hubXY.y + 5}" text-anchor="middle" font-size="13">🏠</text>
    <text x="${hubXY.x}" y="${hubXY.y + 34}" text-anchor="middle" class="map-hub-label">FarmDirect Hub</text>
  </g>`;
  svg += '</svg>';
  el.innerHTML = svg;
}

function fdHighlightStop(g) {
  g.querySelector('circle').setAttribute('r', '17');
  const info = document.getElementById('map-stop-info');
  if (info) {
    info.innerHTML = `<b>${g.dataset.order}</b> · ${g.dataset.buyer || ''} <span class="text-muted-fd">— ${g.dataset.area || ''}</span>`;
  }
}
function fdClearHighlight() {
  document.querySelectorAll('.map-stop circle').forEach(c => c.setAttribute('r', '13'));
  const info = document.getElementById('map-stop-info');
  if (info) info.textContent = 'Hover a numbered stop to inspect the delivery.';
}
