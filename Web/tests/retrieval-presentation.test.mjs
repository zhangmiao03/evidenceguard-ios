import test from 'node:test';
import assert from 'node:assert/strict';
import {candidateFrames,nearestFrame,playbackPosition} from '../src/dashboard/retrievalPresentation.mjs';

test('retrieval picture lineage rejects other recordings, windows, stale indices and out-of-window frames',()=>{
  const base={kind:'frame',recordingId:'v',clipId:'clip',signature:'sig',frameOffsetSeconds:40};
  const frame=(patch)=>({name:'media_video_segments',data:{...base,...patch}});
  const rows=[frame({}),frame({frameOffsetSeconds:32}),frame({recordingId:'other'}),frame({clipId:'adjacent'}),frame({signature:'old'}),frame({frameOffsetSeconds:51}),frame({kind:'video'})];
  const q={signatureCompatible:true,indexSignature:'sig',source:{recordingId:'v'}},v={id:'clip',recordingId:'v',segmentStart:30,segmentEnd:50};
  const frames=candidateFrames(rows,q,v);
  assert.deepEqual(frames.map(r=>r.data.frameOffsetSeconds),[32,40]);
  assert.equal(nearestFrame(frames,41).data.frameOffsetSeconds,40);
  assert.deepEqual(candidateFrames(rows,{...q,signatureCompatible:false},v),[]);
  assert.deepEqual(candidateFrames(rows,{...q,indexSignature:undefined},v),[]);
  assert.deepEqual(candidateFrames(rows,{...q,source:{recordingId:'other'}},v),[]);
  assert.equal(playbackPosition(-1,65),0);assert.equal(playbackPosition(99,65),65);assert.equal(playbackPosition(NaN,65),0);
});
