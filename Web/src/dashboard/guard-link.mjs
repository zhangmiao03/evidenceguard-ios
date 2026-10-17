// Link explicit persisted evidence receipts, never infer identities or proximity.
export function guardModelCall(evidence, rows) {
  const traceId = evidence.guardRunId;
  if (typeof traceId !== 'string' || !traceId.startsWith('guard-')) return null;
  const receipt = rows.find(r => r.name === 'guard.finished' && r.traceId === traceId
    && !r.data.privateContent && r.data.disposition === 'committed'
    && r.data.alertPublished === true && r.data.evidenceId === evidence.id);
  return receipt ? rows.find(r => r.kind === 'model' && r.traceId === traceId && !r.data.privateContent) || null : null;
}
