// Exact recording, clip and index signature only; never borrow adjacent footage.
export function candidateFrames(rows, query, candidate) {
  if(!query?.signatureCompatible||!query?.indexSignature||!candidate)return [];
  return rows.filter(r=>r.name==='media_video_segments'&&r.data.kind==='frame'&&
    r.data.recordingId===candidate.recordingId&&r.data.recordingId===query.source?.recordingId&&
    r.data.clipId===(candidate.clipId||candidate.id)&&r.data.signature===query.indexSignature&&
    Number.isFinite(r.data.frameOffsetSeconds)&&r.data.frameOffsetSeconds>=candidate.segmentStart&&
    r.data.frameOffsetSeconds<=candidate.segmentEnd).sort((a,b)=>a.data.frameOffsetSeconds-b.data.frameOffsetSeconds);
}
export function nearestFrame(frames, seconds) {
  if(!Number.isFinite(seconds))return frames[0];
  return [...frames].sort((a,b)=>Math.abs(a.data.frameOffsetSeconds-seconds)-Math.abs(b.data.frameOffsetSeconds-seconds))[0];
}
export function playbackPosition(value, duration) {
  return Math.max(0,Math.min(Number.isFinite(duration)?duration:Infinity,Number.isFinite(value)?value:0));
}
