import {useEffect,useRef,useState} from 'react';
export type Media = {assetId?:string;previewUrl?:string;kind?:string;mime?:string;status?:string;provenance?:string;position?:string};
const allowed = /^\/dashboard\/api\/media\/(demo|team|review)\/[a-f0-9]{64}$/;
export function MediaPreview({items,title='记录画面',seek}:{items?:Media[];title?:string;seek?:number}){
  const [open,setOpen]=useState<Media|null>(null),[failed,setFailed]=useState<Record<string,boolean>>({});
  const dialog=useRef<HTMLDialogElement>(null);
  useEffect(()=>{if(open)dialog.current?.showModal();else dialog.current?.close();},[open]);
  const media=(items||[]).filter((m):m is Media & {previewUrl:string}=>!!m && allowed.test(m.previewUrl||''));
  const player=(m:Media & {previewUrl:string},large=false)=>m.kind==='video'?<video key={m.previewUrl} controls playsInline preload="metadata" aria-label={title} src={m.previewUrl+(seek?`#t=${seek}`:'#t=0.1')} onLoadedMetadata={e=>{if(seek)e.currentTarget.currentTime=seek;}} onError={()=>setFailed(v=>({...v,[m.previewUrl]:true}))}/>:<img src={m.previewUrl} alt={title} loading={large?'eager':'lazy'} onError={()=>setFailed(v=>({...v,[m.previewUrl]:true}))}/>;
  if(!media.length)return <p className="eg-media-unavailable">{items?.some(m=>m?.provenance==='exact_model_input')?'该次输入副本已过期或超出采集上限。':'此记录未保存可展示的原始媒体。'}</p>;
  return <div className="eg-media-previews">{media.map((m,i)=><figure key={m.previewUrl+String(i)}>{failed[m.previewUrl]?<p>媒体副本暂不可用，请刷新数据。</p>:m.kind==='video'?player(m):<button className="eg-media-imagebutton" onClick={()=>setOpen(m)} aria-label={`${title} · 放大图片 ${i+1}`}>{player(m)}<span>放大查看</span></button>}<figcaption><span>{m.provenance==='executor_input'?'传给 AI 执行器的原图':m.provenance==='exact_model_input'?'本次模型提交原件':m.provenance==='stored_recording'?'入库录像':'事件来源图片'}{media.length>1?` · ${i+1}/${media.length}`:''}</span><a href={m.previewUrl} download={m.kind==='video'?'录像.mp4':'画面.jpg'}>下载{m.kind==='video'?'视频':'图片'}</a></figcaption></figure>)}
    <dialog className="eg-media-lightbox" ref={dialog} onCancel={()=>setOpen(null)} onClick={e=>{if(e.target===e.currentTarget)setOpen(null);}}><button onClick={()=>setOpen(null)} aria-label="关闭图片预览">关闭 ×</button>{open&&allowed.test(open.previewUrl||'')&&player(open as Media & {previewUrl:string},true)}<p>{title}</p></dialog>
  </div>;
}
