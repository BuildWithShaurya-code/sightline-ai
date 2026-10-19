import React from 'react';

/** Open a real captured photo immediately; persistence may finish on the detail screen. */
export function ThreatWarningActions({opening,incidentReady,onReview,onDismiss}:{opening:boolean;incidentReady:boolean;onReview:()=>void;onDismiss:()=>void}) {
  return <div className="grid grid-cols-2 gap-2 mt-3">
    <button type="button" onClick={onReview} disabled={opening||!incidentReady} className="min-h-[44px] rounded-xl bg-[#1c2b3c] border border-white/30 text-xs font-bold disabled:opacity-50">{opening?'Confirming…':'CONFIRM THREAT'}</button>
    <button type="button" onClick={onDismiss} disabled={opening} className="min-h-[44px] rounded-xl bg-[#b91c28] text-xs font-bold">Dismiss warning</button>
  </div>;
}
