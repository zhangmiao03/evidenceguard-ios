// Counts and groupings always derive from selected records, never demo claims.
export function clipGroups(rows, recordingId) {
  const groups=new Map();
  for(const r of rows.filter(r=>r.name==='media_video_segments'&&r.data.recordingId===recordingId)){
    const d=r.data,key=d.clipId||d.id;
    const g=groups.get(key)||{id:key,start:d.start,end:d.end,rows:[],frames:[],videos:[]};
    g.rows.push(r);(d.kind==='frame'?g.frames:g.videos).push(r);groups.set(key,g);
  }
  return [...groups.values()].sort((a,b)=>a.start-b.start).map(g=>({...g,frames:g.frames.sort((a,b)=>a.data.frameOffsetSeconds-b.data.frameOffsetSeconds)}));
}
export function embeddingPurpose(row, rows) {
  if(row.data.privateContent)return 'private';
  const prompt=rows.find(p=>p.id===row.data.promptId);
  if(prompt?.data.privateContent)return 'private';
  const instruction=prompt?.data.request?.instructions;
  if(typeof instruction!=='string')return 'unknown';
  if(instruction.startsWith('Instruction:Compress the ')||instruction.startsWith('Instruction:Represent the visible actions'))return 'corpus';
  if(instruction.startsWith('Target_modality:'))return 'query';
  return 'unknown';
}
export function retrievalRows(rows) {
  return rows.filter(r=>r.name==='vector.search'||(r.name==='tool.finished'&&['search_recordings','search_video','search_videos'].includes(r.data.tool)&&!rows.some(s=>s.name==='vector.search'&&s.traceId===r.traceId)));
}
