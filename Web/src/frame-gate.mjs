// Correlate server requests with a subsequent SDK callback, never a cached cover.
export class FrameGate {
  sequence = 0;
  frame = null;
  lastTimestamp = null;
  accept(frame, now = Date.now()) {
    if (
      !frame?.blob?.size ||
      frame.width <= 0 ||
      frame.height <= 0 ||
      !Number.isFinite(frame.timestamp)
    )
      return false;
    if (this.lastTimestamp !== null && frame.timestamp <= this.lastTimestamp)
      return false;
    this.lastTimestamp = frame.timestamp;
    this.frame = {
      ...frame,
      sequence: ++this.sequence,
      sampledAt: now / 1000,
      localAt: now,
    };
    return true;
  }
  after(command, receivedSequence, now = Date.now()) {
    const f = this.frame;
    return f &&
      command.deadline * 1000 > now &&
      now - f.localAt < 2000 &&
      f.sequence > Math.max(command.afterSequence, receivedSequence)
      ? f
      : null;
  }
}
