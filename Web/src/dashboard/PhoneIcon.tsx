/** Small, consistent outline icons; no platform font or emoji dependency. */
export function PhoneIcon({name}:{name:string}){
 const paths:Record<string,React.ReactNode>={
  chat:<><path d="M20 11a7 7 0 0 1-7 7H8l-5 3 1.5-5A7 7 0 1 1 20 11Z"/><path d="M8 10h.01M12 10h.01M16 10h.01" strokeWidth="3"/></>,
  camera:<><rect x="3" y="6" width="12" height="13" rx="3"/><path d="m15 10 6-3v11l-6-3"/></>,
  tasks:<><path d="m3 5 2 2 3-4m-5 9 2 2 3-4m-5 9 2 2 3-4M12 5h9M12 12h9M12 19h9"/></>,
  memory:<><path d="M9 19H6l-1-5-2-2 2-2A8 8 0 1 1 19 16v5M9 21v-5"/><path d="m12 6 .8 2.2L15 9l-2.2.8L12 12l-.8-2.2L9 9l2.2-.8Z"/></>,
  profile:<><circle cx="12" cy="12" r="9"/><circle cx="12" cy="9" r="3"/><path d="M5 18c2-5 12-5 14 0"/></>,
  bell:<><path d="M5 17c2-2 2-3 2-7a5 5 0 0 1 10 0c0 4 0 5 2 7Z"/><path d="M10 21h4M12 3V2"/></>,
  sparkle:<><path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4Z"/><path d="M20 2v4m-2-2h4"/></>,
  wifi:<><path d="M2 9a16 16 0 0 1 20 0M5 13a11 11 0 0 1 14 0M9 17a5 5 0 0 1 6 0"/><circle cx="12" cy="21" r="1" fill="currentColor"/></>,
  signal:<><path d="M3 18v-3m5 3V11m5 7V7m5 11V3" strokeWidth="3"/></>,
  battery:<><rect x="2" y="6" width="17" height="12" rx="3"/><path d="M22 10v4"/><rect x="5" y="9" width="11" height="6" rx="1" fill="currentColor" stroke="none"/></>,
  mic:<><rect x="8" y="2" width="8" height="13" rx="4"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4m-4 0h8"/></>,
  arrow:<path d="M12 20V4m-6 6 6-6 6 6"/>,
  shield:<><path d="m12 2 8 3v6c0 5-8 11-8 11S4 16 4 11V5Z"/><path d="m8 11 3 3 5-6"/></>,
 };
 return <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]||paths.sparkle}</svg>;
}
