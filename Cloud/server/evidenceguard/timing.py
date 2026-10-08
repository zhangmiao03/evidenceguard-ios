"""Seconds-based evidence confirmation; observations do not prove continuity between samples."""
def accumulate(candidate,key,at,proof,interval):
    if candidate.get('proof')==proof:return candidate
    gap=at-candidate.get('at',-1e20)
    if candidate and gap<interval-1e-6:return candidate
    since=candidate.get('since',at) if candidate.get('key')==key and gap<=interval*1.5 else at
    return dict(key=key,at=at,since=since,proof=proof,span=max(0,at-since))
