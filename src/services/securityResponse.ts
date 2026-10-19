import { Incident } from '../types/sightline.ts';
export type ResponseKind = 'call_opened' | 'whatsapp_opened' | 'summary_copied' | 'summary_shared' | 'contact_confirmed' | 'note' | 'resolved' | 'false_alarm';
export type Recipient = 'security' | 'police' | 'owner';
export interface ResponseEvent { id: string; kind: ResponseKind; recipient: Recipient; detail: string; createdAt: string; }
export interface SecurityResponse { status: string; events: ResponseEvent[]; confirmedContacts?: ('security'|'police')[]; }
export interface ResponseContacts { securityName: string; securityPhone: string; policePhone: string; siteAddress: string; whatsappPhone?: string; }
export const defaultContacts: ResponseContacts = { securityName: '', securityPhone: '', policePhone: '112', siteAddress: '' };
export const falseAlarmReasons = ['Family member', 'Pet', 'Delivery', 'Model error', 'Other'];
export function shortIncidentSummary(inc: Incident, contacts: ResponseContacts): string {
 const labels=[...new Set(inc.detections.map(d=>d.classId))].join(', ');
 return `${inc.status==='confirmed'?'The owner confirmed a security threat':'A security incident was reported'} at ${contacts.siteAddress || inc.zone || 'the monitored location'} on ${new Date(inc.createdAt).toLocaleString()}. ${labels ? `The model detected ${labels}.` : 'This was an owner-reported alert.'} Camera: ${inc.channel || inc.sourceId}. ${inc.frames.length ? `${inc.frames.length} evidence photo(s) are saved for review.` : 'No evidence photos are available.'} Assistance is requested; contact the owner for details.`;
}
export function contactConfirmed(response: SecurityResponse, who: Recipient): boolean {
 return !!response.confirmedContacts?.includes(who as 'security'|'police') || response.events.some(e=>e.kind==='contact_confirmed' && e.recipient===who);
}
export function reportForIncident(inc: Incident, contacts: ResponseContacts, description: string): string {
  const detections = [...new Set(inc.detections.map(d => `${d.classId} (${Math.round(d.confidence*100)}%)`))].join(', ');
  return ['SightLine incident report', `Incident: ${inc.id}`, `Time: ${new Date(inc.createdAt).toLocaleString()} (${Intl.DateTimeFormat().resolvedOptions().timeZone})`,
    `Location: ${contacts.siteAddress || 'Exact address not provided — confirm with owner'}`, `Camera / zone: ${inc.channel || inc.sourceId} / ${inc.zone || 'Not specified'}`,
    `Reported event: ${inc.title || 'Security incident'}`, `Model detections: ${detections || 'None recorded; operator-reported alert'}`,
    `Detection rule: ${inc.reason || 'Not recorded'}`, `Review: ${inc.status}`, `Evidence: ${inc.frames.length ? inc.frames.length+' captured photo(s), available separately' : 'No evidence captured'}`,
    `Owner description: ${description.trim() || 'No additional description'}`, 'Detections require human review; they do not establish theft.'].join('\n');
}
export function whatsappUrl(phone: string, report: string): string {
  const digits = phone.replace(/^\+/, '');
  if (!/^[1-9][0-9]{6,14}$/.test(digits)) throw new Error('Add security phone with country code, for example +91 followed by the number.');
  return `https://wa.me/${digits}?text=${encodeURIComponent(report)}`;
}
export function eventLabel(e: ResponseEvent): string {
 const who = e.recipient === 'police' ? 'Police' : e.recipient === 'security' ? 'Security' : 'Owner';
 const labels: Record<ResponseKind, string> = {call_opened: `${who} call opened`, whatsapp_opened: 'WhatsApp opened for security', summary_copied: 'Police report copied', summary_shared: 'Summary shared · confirmed by you', contact_confirmed: `Spoke to ${who.toLowerCase()} · confirmed by you`, note: 'Owner note', resolved: 'Resolved · confirmed by you', false_alarm: 'False alarm · confirmed by you'};
 return labels[e.kind];
}
