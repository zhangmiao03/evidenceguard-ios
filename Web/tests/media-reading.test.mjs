import test from 'node:test';
import assert from 'node:assert/strict';
import {clipGroups,embeddingPurpose,retrievalRows} from '../src/dashboard/mediaReading.mjs';
test('four vector units in one window count as one clip and never join another recording',()=>{
  const rows=[...['video','frame','frame','frame'].map((kind,i)=>({name:'media_video_segments',data:{id:String(i),recordingId:'a',clipId:'c',start:0,end:20,kind,frameOffsetSeconds:3-i}})),{name:'media_video_segments',data:{id:'x',recordingId:'b',clipId:'c',kind:'video'}}];
  const groups=clipGroups(rows,'a');assert.equal(groups.length,1);assert.equal(groups[0].videos.length,1);assert.equal(groups[0].frames.length,3);assert.deepEqual(groups[0].frames.map(r=>r.data.frameOffsetSeconds),[0,1,2]);
});
test('corpus images are not query images; unknown and private inputs stay distinct',()=>{
  const row={data:{promptId:'p'}};
  assert.equal(embeddingPurpose(row,[{id:'p',data:{request:{instructions:'Instruction:Compress the image into one word.\nQuery:'}}}]),'corpus');
  assert.equal(embeddingPurpose(row,[{id:'p',data:{request:{instructions:'Target_modality: image/video.'}}}]),'query');
  assert.equal(embeddingPurpose(row,[]),'unknown');
  assert.equal(embeddingPurpose({...row,data:{privateContent:true}},[]),'private');
});
test('private retrieval remains visible as a diagnostic, without double counting its tool receipt',()=>{
  const rows=[{name:'vector.search',traceId:'x',data:{privateContent:true}},{name:'tool.finished',traceId:'x',data:{tool:'search_recordings'}}];
  assert.equal(retrievalRows(rows).length,1);assert.equal(retrievalRows(rows)[0].data.privateContent,true);
});
