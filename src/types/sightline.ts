/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { ModelClass } from '../constants/classes.ts';

export type ScreenId =
  | 'operator-login'
  | 'threat-detail'
  | 'dismiss-incident'
  | 'dashboard'
  | 'security-setup'
  | 'security-response'
  | 'dispatch-receipt'
  | 'detection-studio'
  | 'history-logs';

export type InputMode = 'upload' | 'live';

export type IncidentStatus = 'unreviewed' | 'confirmed' | 'dismissed';

export type DispatchStatus =
  | 'not_sent'
  | 'pending'
  | 'sent'
  | 'simulated'
  | 'failed'
  | 'cancelled'
  | 'uncertain';

export interface Detection {
  classId: ModelClass;
  confidence: number; // 0 to 1
  box?: [number, number, number, number]; // [x1, y1, x2, y2]
  frame_index?: number;
  frameIndex?: number;
  frame_width?: number;
  evidence_id?: string;
  video_offset_seconds?: number;
}

export interface Frame {
  id: string;
  timeSeconds: number;
  imageDataUrl: string;
}

export interface Incident {
  id: string;
  sourceId: string;
  createdAt: string; // ISO string e.g. 2026-10-16T10:45:00.000Z
  status: IncidentStatus;
  frames: Frame[];
  detections: Detection[];
  responseStatus?: string;
  reason?: string;
  review_reason?: string;
  dispatchId?: string;
  title?: string;
  channel?: string;
  zone?: string;
  durationSeconds?: number;
  thumbnail?: string;
}

export interface Dispatch {
  id: string;
  incidentId: string;
  status: DispatchStatus;
  provider?: string;
  provider_reference?: string;
  is_simulated?: boolean;
  destination_reference?: string;
  channel?: string;
  error?: string;
  failure_details?: string;
  createdAt?: string;
  deliveredAt?: string;
  cancelledAt?: string;
  callSign?: string;
  etaMinutes?: number;
  attempt_count?: number;
}

export interface ThreatTarget {
  id: ModelClass;
  label: string;
  type: string;
  active: boolean;
  confidence?: number;
}

export interface SingleImageInferenceResponse {
  request_id?: string;
  model_version: string;
  model_sha256: string;
  device: string;
  original_width: number;
  original_height: number;
  targets: ModelClass[];
  confidence_threshold: number;
  detections_count: number;
  detections: Detection[];
  timings: {
    decode_ms: number;
    inference_ms: number;
    serialization_ms: number;
    total_ms: number;
  };
  timestamp: string;
}

