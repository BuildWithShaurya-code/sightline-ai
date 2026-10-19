/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Incident, Dispatch, IncidentStatus, DispatchStatus } from '../types/sightline.ts';
import { MODEL_CLASSES } from '../constants/classes.ts';

const STORAGE_KEY_INCIDENTS = 'sightline_incidents_v2';
const STORAGE_KEY_DISPATCHES = 'sightline_dispatches_v2';
const LEGACY_LOGS_KEY = 'sightline_evidence_logs';
const MAX_INCIDENTS = 20;

/**
 * Type-guard validating whether an unknown object adheres to the Incident schema.
 */
export function isValidIncident(item: unknown): item is Incident {
  if (!item || typeof item !== 'object') return false;
  const inc = item as Record<string, unknown>;

  if (typeof inc.id !== 'string' || !inc.id.trim()) return false;
  if (typeof inc.sourceId !== 'string') return false;
  if (typeof inc.createdAt !== 'string' || isNaN(Date.parse(inc.createdAt))) return false;

  const validStatuses: IncidentStatus[] = ['unreviewed', 'confirmed', 'dismissed'];
  if (!validStatuses.includes(inc.status as IncidentStatus)) return false;

  if (!Array.isArray(inc.frames)) return false;
  for (const f of inc.frames) {
    if (!f || typeof f !== 'object') return false;
    if (typeof f.id !== 'string') return false;
    if (typeof f.timeSeconds !== 'number') return false;
    if (typeof f.imageDataUrl !== 'string') return false;
  }

  if (!Array.isArray(inc.detections)) return false;
  for (const d of inc.detections) {
    if (!d || typeof d !== 'object') return false;
    if (!MODEL_CLASSES.includes(d.classId)) return false;
    if (typeof d.confidence !== 'number' || d.confidence < 0 || d.confidence > 1) return false;
  }

  return true;
}

/**
 * Type-guard validating whether an unknown object adheres to the Dispatch schema.
 */
export function isValidDispatch(item: unknown): item is Dispatch {
  if (!item || typeof item !== 'object') return false;
  const disp = item as Record<string, unknown>;

  if (typeof disp.id !== 'string' || !disp.id.trim()) return false;
  if (typeof disp.incidentId !== 'string' || !disp.incidentId.trim()) return false;

  const validStatuses: DispatchStatus[] = [
    'not_sent',
    'pending',
    'sent',
    'simulated',
    'failed',
    'cancelled',
    'uncertain',
  ];
  if (!validStatuses.includes(disp.status as DispatchStatus)) return false;

  return true;
}

/**
 * Creates a downscaled JPEG thumbnail dataURL from an image or video frame
 * to keep storage far below browser quota limits.
 */
export async function createSmallThumbnail(
  source: CanvasImageSource,
  maxWidth = 320,
  maxHeight = 180,
  quality = 0.65
): Promise<string> {
  try {
    const canvas = document.createElement('canvas');
    let width = 0;
    let height = 0;

    if (source instanceof HTMLVideoElement) {
      width = source.videoWidth || 640;
      height = source.videoHeight || 360;
    } else if (source instanceof HTMLImageElement) {
      width = source.naturalWidth || 640;
      height = source.naturalHeight || 360;
    } else if (source instanceof HTMLCanvasElement) {
      width = source.width;
      height = source.height;
    }

    if (width === 0 || height === 0) {
      width = 640;
      height = 360;
    }

    const scale = Math.min(maxWidth / width, maxHeight / height, 1);
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));

    const ctx = canvas.getContext('2d');
    if (!ctx) return '';

    ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', quality);
  } catch (err) {
    console.warn('Failed to generate thumbnail, returning empty string:', err);
    return '';
  }
}

/**
 * Safe parser for stored incidents. Discards invalid records and never throws.
 */
export function getIncidents(): Incident[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_INCIDENTS);
    if (!raw) {
      // Check legacy format once
      const legacy = localStorage.getItem(LEGACY_LOGS_KEY);
      if (legacy) {
        try {
          const parsed = JSON.parse(legacy);
          if (Array.isArray(parsed)) {
            const converted: Incident[] = parsed
              .map((item): Incident | null => {
                if (!item || typeof item !== 'object') return null;
                const rec = item as Record<string, any>;
                const id = String(rec.id || `INC-${Date.now()}`);
                return {
                  id,
                  sourceId: String(rec.channel || rec.title || 'legacy_clip'),
                  createdAt: new Date().toISOString(),
                  status: rec.status === 'confirmed' ? 'confirmed' : 'unreviewed',
                  title: String(rec.title || 'Recorded Incident'),
                  channel: String(rec.channel || 'CAM_01'),
                  zone: 'Not available',
                  thumbnail: typeof rec.thumbnail === 'string' ? rec.thumbnail : '',
                  frames: Array.isArray(rec.frames)
                    ? rec.frames.map((f: any, idx: number) => ({
                        id: String(f.id || `f-${idx}`),
                        timeSeconds: idx,
                        imageDataUrl: String(f.dataUrl || ''),
                      }))
                    : [],
                  detections: [],
                };
              })
              .filter((x): x is Incident => x !== null && isValidIncident(x));

            if (converted.length > 0) {
              localStorage.setItem(STORAGE_KEY_INCIDENTS, JSON.stringify(converted));
              return converted.slice(0, MAX_INCIDENTS);
            }
          }
        } catch {
          // ignore legacy error
        }
      }
      return [];
    }

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    const validIncidents = parsed.filter(isValidIncident);
    return validIncidents.slice(0, MAX_INCIDENTS);
  } catch (err) {
    console.error('SafeStorage: getIncidents error:', err);
    return [];
  }
}

/**
 * Fetch a single incident by ID.
 */
export function getIncidentById(id: string): Incident | null {
  if (!id) return null;
  const list = getIncidents();
  return list.find((inc) => inc.id === id) || null;
}

/**
 * Safe writer for an incident record. Enforces retention limit and never throws.
 */
export function saveIncident(incident: Incident): boolean {
  try {
    if (!isValidIncident(incident)) {
      console.error('SafeStorage: Refused to save invalid incident:', incident);
      return false;
    }

    const current = getIncidents();
    const filtered = current.filter((i) => i.id !== incident.id);
    const updated = [incident, ...filtered].slice(0, MAX_INCIDENTS);

    localStorage.setItem(STORAGE_KEY_INCIDENTS, JSON.stringify(updated));
    return true;
  } catch (err) {
    console.error('SafeStorage: saveIncident failed (e.g. quota exceeded):', err);
    return false;
  }
}

/**
 * Partial update for an existing incident.
 */
export function updateIncident(id: string, updates: Partial<Incident>): boolean {
  try {
    const current = getIncidents();
    const index = current.findIndex((i) => i.id === id);
    if (index === -1) return false;

    const merged = { ...current[index], ...updates, id };
    if (!isValidIncident(merged)) {
      console.error('SafeStorage: Updated incident violates schema:', merged);
      return false;
    }

    current[index] = merged;
    localStorage.setItem(STORAGE_KEY_INCIDENTS, JSON.stringify(current));
    return true;
  } catch (err) {
    console.error('SafeStorage: updateIncident failed:', err);
    return false;
  }
}

/**
 * Deletes an incident record by ID.
 */
export function deleteIncident(id: string): boolean {
  try {
    const current = getIncidents();
    const filtered = current.filter((i) => i.id !== id);
    localStorage.setItem(STORAGE_KEY_INCIDENTS, JSON.stringify(filtered));
    return true;
  } catch (err) {
    console.error('SafeStorage: deleteIncident failed:', err);
    return false;
  }
}

/**
 * Dispatches repository: get all dispatches safely.
 */
export function getDispatches(): Dispatch[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_DISPATCHES);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isValidDispatch);
  } catch (err) {
    console.error('SafeStorage: getDispatches error:', err);
    return [];
  }
}

/**
 * Get dispatch record associated with a given incident ID.
 */
export function getDispatchByIncidentId(incidentId: string): Dispatch | null {
  if (!incidentId) return null;
  const list = getDispatches();
  return list.find((d) => d.incidentId === incidentId) || null;
}

/**
 * Save or update a Dispatch record.
 */
export function saveDispatch(dispatch: Dispatch): boolean {
  try {
    if (!isValidDispatch(dispatch)) {
      console.error('SafeStorage: Invalid dispatch:', dispatch);
      return false;
    }

    const current = getDispatches();
    const filtered = current.filter((d) => d.id !== dispatch.id && d.incidentId !== dispatch.incidentId);
    const updated = [dispatch, ...filtered].slice(0, MAX_INCIDENTS);

    localStorage.setItem(STORAGE_KEY_DISPATCHES, JSON.stringify(updated));
    return true;
  } catch (err) {
    console.error('SafeStorage: saveDispatch error:', err);
    return false;
  }
}

/**
 * Clears all local application data (for error boundary and manual hard reset).
 */
export function clearAllData(): void {
  try {
    localStorage.removeItem(STORAGE_KEY_INCIDENTS);
    localStorage.removeItem(STORAGE_KEY_DISPATCHES);
    localStorage.removeItem(LEGACY_LOGS_KEY);
    localStorage.removeItem('sightline_video_name');
    localStorage.removeItem('sightline_latest_frame');
    localStorage.removeItem('sightline_auth_token');
    sessionStorage.clear();
  } catch (err) {
    console.warn('SafeStorage: clearAllData error:', err);
  }
}
