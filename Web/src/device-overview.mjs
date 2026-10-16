// Event-only discovery intentionally does not disclose the SDK SN used to start
// a foreground stream. Only /api/devices can supply that live identity.
export function mergeDevices(events = [], live = []) {
  const byID = new Map(events.map(d => [d.id, { ...d, sn: "" }]));
  for (const d of live) byID.set(d.id, { ...byID.get(d.id), ...d });
  return [...byID.values()];
}
