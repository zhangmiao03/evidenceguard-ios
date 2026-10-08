export function normalizedBox(start, end) {
  const clamp = (n) => Math.max(0, Math.min(1, n));
  const a = { x: clamp(start.x), y: clamp(start.y) };
  const b = { x: clamp(end.x), y: clamp(end.y) };
  const box = {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    width: Math.abs(a.x - b.x),
    height: Math.abs(a.y - b.y),
  };
  return box.width >= 0.01 && box.height >= 0.01 ? box : null;
}
