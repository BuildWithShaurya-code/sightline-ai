/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Incident, Dispatch, SingleImageInferenceResponse, IncidentStatus } from '../types/sightline.ts';
import { ModelClass } from '../constants/classes.ts';
import { isValidIncident, isValidDispatch } from './storage.ts';
import { getAccessToken, getCurrentAccountId } from './auth.ts';
import {incidentMemory} from './incidentMemory.ts';
export function getCachedIncident(id:string):Incident|null{return incidentMemory.get(getCurrentAccountId(),id);}
export function clearIncidentMemory(){incidentMemory.clear();}
function incidentRequest(){const owner=getCurrentAccountId();return {owner,ticket:incidentMemory.ticket(owner)};}
function rememberIncident(request:ReturnType<typeof incidentRequest>,incident:Incident){if(request.owner===getCurrentAccountId())incidentMemory.put(request.owner,request.ticket,incident);return incident;}

/**
 * SightLine AI - Typed Frontend API Client Foundation
 * Provides configurable base URL, timeout handling via AbortController,
 * structured error models, automatic bearer token injection, and runtime validation.
 */

export interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  headers?: Record<string, string>;
  credentials?: RequestCredentials;
}

export class ApiError extends Error {
  public readonly status: number;
  public readonly errorCode: string;
  public readonly details: Record<string, unknown>;
  public readonly requestId?: string;

  constructor(
    message: string,
    status = 500,
    errorCode = 'INTERNAL_ERROR',
    details: Record<string, unknown> = {},
    requestId?: string
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.errorCode = errorCode;
    this.details = details;
    this.requestId = requestId;
  }
}

export class BackendDisconnectedError extends ApiError {
  constructor(message = 'Backend not connected - running in standalone demo mode.') {
    super(message, 0, 'BACKEND_DISCONNECTED');
    this.name = 'BackendDisconnectedError';
  }
}

export class TimeoutError extends ApiError {
  constructor(message = 'API request timed out.') {
    super(message, 408, 'REQUEST_TIMEOUT');
    this.name = 'TimeoutError';
  }
}

export class NetworkError extends ApiError {
  constructor(message = 'Network error or server unreachable.') {
    super(message, 0, 'NETWORK_ERROR');
    this.name = 'NetworkError';
  }
}

export class ValidationError extends ApiError {
  constructor(message = 'Response failed schema validation.', details: Record<string, unknown> = {}) {
    super(message, 422, 'VALIDATION_ERROR', details);
    this.name = 'ValidationError';
  }
}

export interface AnalysisJob {
  id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';
  progress?: number;
  incidentId?: string;
  error?: string;
}

export interface JobCancelResponse {
  jobId: string;
  status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';
  cancellation_requested: boolean;
  message: string;
}

export interface HealthLiveResponse {
  status: string;
  service: string;
  version: string;
  timestamp: string;
}

export interface HealthReadyComponent {
  status: string;
  ready: boolean;
  [key: string]: unknown;
}

export interface HealthReadyResponse {
  status: 'ready' | 'degraded';
  phase: number;
  phase_description: string;
  timestamp: string;
  components: {
    api_foundation: HealthReadyComponent;
    media_storage: HealthReadyComponent;
    model_checkpoint: HealthReadyComponent;
    inference_service: HealthReadyComponent;
    video_worker: HealthReadyComponent;
    database: HealthReadyComponent;
  };
}

export interface ModelCapabilities {
  model_id: string;
  architecture: string;
  framework: string;
  supported_classes: ModelClass[];
  class_map: Record<string, ModelClass>;
  default_confidence_threshold: number;
  recommended_sample_rate_sec: number;
  readiness: {
    compatible: boolean;
    checkpoint_found: boolean;
    file_size_bytes: number;
    sha256: string;
    model_loaded_in_api: boolean;
  };
}

export interface UploadVideoResponse {
  sourceId: string;
  videoUrl: string;
}

export interface StartAnalysisResponse {
  jobId: string;
}

export interface CancelDispatchResponse {
  success: boolean;
  dispatch: Dispatch;
  message?: string;
}

export interface PaginatedIncidentsResponse {
  items: Incident[];
  pagination: {
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
  };
}

export interface UserProfileResponse {
  id: string;
  email?: string;
  role: string;
  operatorId: string;
}

const DEFAULT_TIMEOUT_MS = 20000;

/**
 * Returns the effective API base URL.
 * Falls back to empty string for same-origin / Vite reverse proxy.
 */
export function getApiBaseUrl(): string {
  const envUrl = import.meta.env.VITE_API_URL;
  if (typeof envUrl === 'string' && envUrl.trim().length > 0) {
    // Callers append /api/v1. Accept either an origin or an API-root setting
    // so local/cloud configuration cannot accidentally double that prefix.
    return envUrl.trim().replace(/\/+$/, '').replace(/\/api\/v1$/, '');
  }
  // When empty, relative same-origin calls (/api/v1/...) are proxied by Vite
  return '';
}

/**
 * Check whether backend is reachable/configured.
 */
export function isBackendConfigured(): boolean {
  return true;
}

function ensureBackendUrl(): string {
  return getApiBaseUrl();
}

/**
 * Core fetch wrapper with timeout, cancellation, automatic Bearer token injection, and error mapping.
 */
async function fetchWithTimeout(
  url: string,
  init: RequestInit = {},
  options: RequestOptions = {}
): Promise<Response> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const callerSignal = options.signal;

  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  let timedOut = false;
  const timeoutPromise = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => {
      timedOut = true;
      controller.abort();
      reject(new TimeoutError(`Request timed out after ${timeoutMs}ms: ${url}`));
    }, timeoutMs);
  });

  const abortListener = () => {
    controller.abort();
  };
  if (callerSignal) {
    if (callerSignal.aborted) controller.abort();
    else callerSignal.addEventListener('abort', abortListener);
  }

  // Inject Bearer token if not explicitly supplied
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(init.headers as Record<string, string>),
    ...options.headers,
  };

  let rejectAbort: (()=>void) | undefined;
  const abortPromise = new Promise<never>((_resolve,reject)=>{
    rejectAbort=()=>reject(new DOMException('Request cancelled','AbortError'));
    if(controller.signal.aborted)rejectAbort();
    else controller.signal.addEventListener('abort',rejectAbort,{once:true});
  });
  try {
    // Include token lookup in the deadline. A stalled session refresh must not
    // leave camera controls waiting indefinitely or send a late stale frame.
    const fetchPromise = (async()=>{
      if (!headers['Authorization']) {
        const token=await getAccessToken();
        if(token)headers['Authorization']=`Bearer ${token}`;
      }
      if(controller.signal.aborted)throw new DOMException('Request cancelled','AbortError');
      return fetch(url,{
        ...init,signal:controller.signal,
        credentials:options.credentials||'same-origin',headers,
      });
    })();
    const response = await Promise.race([fetchPromise, timeoutPromise,abortPromise]);
    return response as Response;
  } catch (err: unknown) {
    if (timedOut) throw new TimeoutError('The server took too long to respond. Please retry.');
    if (err instanceof TimeoutError) {
      throw err;
    }
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiError('Request aborted by caller', 0, 'ABORTED');
    }
    if (err instanceof TypeError) {
      throw new NetworkError(`Network connection failed for: ${url}`);
    }
    throw new ApiError(err instanceof Error ? err.message : 'Unknown fetch error');
  } finally {
    if(rejectAbort)controller.signal.removeEventListener('abort',rejectAbort);
    if (timeoutId !== null) {
      clearTimeout(timeoutId);
    }
    if (callerSignal) {
      callerSignal.removeEventListener('abort', abortListener);
    }
  }
}

/**
 * Parse and validate JSON response from backend, throwing structured ApiError on failure.
 */
async function handleResponse<T>(res: Response, url: string): Promise<T> {
  const requestId = res.headers.get('X-Request-ID') || undefined;

  let body: any = null;
  const contentType = res.headers.get('Content-Type') || '';
  if (contentType.includes('application/json')) {
    try {
      body = await res.json();
    } catch {
      body = null;
    }
  }

  if (!res.ok) {
    const errorCode = (body && typeof body.error === 'string') ? body.error : `HTTP_${res.status}`;
    const message = (body && typeof body.message === 'string')
      ? body.message
      : `Request failed with HTTP ${res.status}: ${res.statusText}`;
    const details = (body && typeof body.details === 'object' && body.details !== null)
      ? body.details
      : {};

    throw new ApiError(message, res.status, errorCode, details, requestId);
  }

  return body as T;
}

// ==============================================================================
// HEALTH & CAPABILITIES
// ==============================================================================

/**
 * Check API process liveness (GET /api/v1/health/live).
 */
export async function checkHealthLive(options?: RequestOptions): Promise<HealthLiveResponse> {
  const base = ensureBackendUrl();
  const res = await fetchWithTimeout(`${base}/api/v1/health/live`, { method: 'GET' }, options);
  const data = await handleResponse<HealthLiveResponse>(res, '/api/v1/health/live');

  if (!data || data.status !== 'live') {
    throw new ValidationError('Invalid liveness response schema', { data });
  }
  return data;
}

/**
 * Check service dependency readiness (GET /api/v1/health/ready).
 */
export async function checkHealthReady(options?: RequestOptions): Promise<HealthReadyResponse> {
  const base = ensureBackendUrl();
  const res = await fetchWithTimeout(`${base}/api/v1/health/ready`, { method: 'GET' }, options);
  const data = await handleResponse<HealthReadyResponse>(res, '/api/v1/health/ready');

  if (!data || typeof data.phase !== 'number' || !data.components) {
    throw new ValidationError('Invalid readiness response schema', { data });
  }
  return data;
}

/**
 * Query neural model capabilities and supported classes (GET /api/v1/model/capabilities).
 */
export async function getModelCapabilities(options?: RequestOptions): Promise<ModelCapabilities> {
  const base = ensureBackendUrl();
  const res = await fetchWithTimeout(`${base}/api/v1/model/capabilities`, { method: 'GET' }, options);
  const data = await handleResponse<ModelCapabilities>(res, '/api/v1/model/capabilities');

  if (!data || !Array.isArray(data.supported_classes)) {
    throw new ValidationError('Invalid capabilities response schema', { data });
  }
  return data;
}

/**
 * Retrieve verified operator profile (GET /api/v1/auth/me).
 */
export async function getMe(options?: RequestOptions): Promise<UserProfileResponse> {
  const base = ensureBackendUrl();
  const res = await fetchWithTimeout(`${base}/api/v1/auth/me`, { method: 'GET' }, options);
  return handleResponse<UserProfileResponse>(res, '/api/v1/auth/me');
}

// ==============================================================================
// VIDEO UPLOAD & PROCESSING PIPELINE
// ==============================================================================

/**
 * Upload a video file to the backend processing pipeline (POST /api/v1/videos/upload).
 */
export async function uploadVideo(
  file: File,
  options?: RequestOptions
): Promise<UploadVideoResponse> {
  const base = ensureBackendUrl();
  if (import.meta.env.VITE_CLOUD_UPLOADS === '1') {
    const begin = await fetchWithTimeout(`${base}/api/v1/videos/uploads`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: file.name, size: file.size }),
    }, options);
    const ticket = await handleResponse<{ sourceId: string; uploadUrl: string }>(begin, '/api/v1/videos/uploads');
    const destination = new URL(ticket.uploadUrl);
    const configured = new URL(import.meta.env.VITE_SUPABASE_URL);
    if (destination.protocol !== 'https:' || destination.origin !== configured.origin) {
      throw new ValidationError('The upload destination could not be verified.');
    }
    // The one-use scoped storage ticket is the authorization; never send an account
    // bearer or privileged API key to a storage URL, and never overwrite an object.
    const uploaded = await fetch(destination.href, {
      method: 'PUT', headers: { 'Content-Type': file.type || 'application/octet-stream', 'x-upsert': 'false' },
      body: file, signal: options?.signal,
    });
    if (!uploaded.ok) throw new ValidationError('The private video upload failed. Please retry.');
    const completed = await fetchWithTimeout(`${base}/api/v1/videos/uploads/${encodeURIComponent(ticket.sourceId)}/complete`, { method: 'POST' }, options);
    return handleResponse<UploadVideoResponse>(completed, '/api/v1/videos/uploads/complete');
  }
  const formData = new FormData();
  formData.append('video', file);

  const res = await fetchWithTimeout(
    `${base}/api/v1/videos/upload`,
    {
      method: 'POST',
      body: formData,
    },
    options
  );

  const data = await handleResponse<UploadVideoResponse>(res, '/api/v1/videos/upload');
  if (!data || typeof data.sourceId !== 'string' || typeof data.videoUrl !== 'string') {
    throw new ValidationError('Invalid upload response payload from backend', { data });
  }

  return { sourceId: data.sourceId, videoUrl: data.videoUrl };
}

/**
 * Start neural model analysis job on a specified video source (POST /api/v1/analysis/start).
 */
export async function startAnalysis(
  sourceId: string,
  targets: ModelClass[],
  confidenceThreshold = 0.25,
  sampleRateSec = 0.5,
  options?: RequestOptions
): Promise<StartAnalysisResponse> {
  const base = ensureBackendUrl();

  const res = await fetchWithTimeout(
    `${base}/api/v1/analysis/start`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sourceId,
        targets,
        confidence_threshold: confidenceThreshold,
        sample_rate_sec: sampleRateSec,
      }),
    },
    options
  );

  const data = await handleResponse<StartAnalysisResponse>(res, '/api/v1/analysis/start');
  if (!data || typeof data.jobId !== 'string') {
    throw new ValidationError('Invalid analysis job payload returned from backend', { data });
  }

  return { jobId: data.jobId };
}

/**
 * Poll job status (GET /api/v1/analysis/jobs/:id).
 */
export async function getJob(jobId: string, options?: RequestOptions): Promise<AnalysisJob> {
  const base = ensureBackendUrl();

  const res = await fetchWithTimeout(
    `${base}/api/v1/analysis/jobs/${encodeURIComponent(jobId)}`,
    { method: 'GET' },
    options
  );

  const data = await handleResponse<AnalysisJob>(res, `/api/v1/analysis/jobs/${jobId}`);
  if (!data || typeof data.id !== 'string' || typeof data.status !== 'string') {
    throw new ValidationError('Malformed job response', { data });
  }

  return {
    id: data.id,
    status: data.status,
    progress: typeof data.progress === 'number' ? data.progress : undefined,
    incidentId: typeof data.incidentId === 'string' ? data.incidentId : undefined,
    error: typeof data.error === 'string' ? data.error : undefined,
  };
}

/**
 * Request cancellation of an analysis job (POST /api/v1/analysis/jobs/:id/cancel).
 */
export async function cancelJob(jobId: string, options?: RequestOptions): Promise<JobCancelResponse> {
  const base = ensureBackendUrl();

  const res = await fetchWithTimeout(
    `${base}/api/v1/analysis/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: 'POST' },
    options
  );

  return handleResponse<JobCancelResponse>(res, `/api/v1/analysis/jobs/${jobId}/cancel`);
}

// ==============================================================================
// INCIDENTS & EVIDENCE
// ==============================================================================

/**
 * Retrieve paginated incidents list (GET /api/v1/incidents).
 */
export interface IncidentListParams {q?:string;status?:IncidentStatus;page?:number;page_size?:number;created_after?:string;}
function incidentListKey(params?:IncidentListParams){return JSON.stringify([params?.q||'',params?.status||'',params?.page||1,params?.page_size||20,params?.created_after||'']);}
export function getCachedIncidents(params?:IncidentListParams):PaginatedIncidentsResponse|null{return incidentMemory.page(getCurrentAccountId(),incidentListKey(params));}
export async function listIncidents(
  params?: {
    q?: string;
    status?: IncidentStatus;
    page?: number;
    page_size?: number;
    created_after?: string;
  },
  options?: RequestOptions
): Promise<PaginatedIncidentsResponse> {
  const request=incidentRequest();
  const base = ensureBackendUrl();
  const query = new URLSearchParams();

  if (params?.q) query.set('q', params.q);
  if (params?.created_after) query.set('created_after', params.created_after);
  if (params?.status) query.set('status', params.status);
  if (params?.page) query.set('page', String(params.page));
  if (params?.page_size) query.set('page_size', String(params.page_size));

  const qs = query.toString();
  const url = `${base}/api/v1/incidents${qs ? `?${qs}` : ''}`;

  const res = await fetchWithTimeout(url, { method: 'GET' }, options);
  const data = await handleResponse<PaginatedIncidentsResponse>(res, url);

  if (!data || !Array.isArray(data.items) || !data.pagination) {
    throw new ValidationError('Malformed incidents list response', { data });
  }

  data.items.forEach(item=>rememberIncident(request,item));
  if(request.owner===getCurrentAccountId())incidentMemory.putPage(request.owner,request.ticket,incidentListKey(params),data);
  return data;
}

/**
 * Retrieve incident details from backend (GET /api/v1/incidents/:id).
 */
export async function getIncident(incidentId: string, options?: RequestOptions): Promise<Incident> {
  if(options?.signal?.aborted)throw new ApiError('Request aborted by caller',0,'ABORTED');
  const cached=getCachedIncident(incidentId);if(cached)return cached;
  const request=incidentRequest();
  const base = ensureBackendUrl();

  const res = await fetchWithTimeout(
    `${base}/api/v1/incidents/${encodeURIComponent(incidentId)}`,
    { method: 'GET' },
    options
  );

  const data = await handleResponse<unknown>(res, `/api/v1/incidents/${incidentId}`);
  if (!isValidIncident(data)) {
    throw new ValidationError('Incident data from backend failed runtime validation', { data });
  }

  return rememberIncident(request,data);
}

/**
 * Update incident review status (PATCH /api/v1/incidents/:id).
 */
export async function reviewIncident(
  incidentId: string,
  status: IncidentStatus,
  reason?: string,
  options?: RequestOptions
): Promise<Incident> {
  incidentMemory.invalidate(getCurrentAccountId(),incidentId);
  const request=incidentRequest();
  const base = ensureBackendUrl();

  const res = await fetchWithTimeout(
    `${base}/api/v1/incidents/${encodeURIComponent(incidentId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, reason }),
    },
    options
  );

  const data = await handleResponse<unknown>(res, `/api/v1/incidents/${incidentId}`);
  if (!isValidIncident(data)) {
    throw new ValidationError('Updated incident failed runtime validation', { data });
  }

  return rememberIncident(request,data);
}

/**
 * Soft-delete incident from history (DELETE /api/v1/incidents/:id).
 */
export async function deleteIncident(
  incidentId: string,
  options?: RequestOptions
): Promise<{ success: boolean; id: string; deleted: boolean }> {
  incidentMemory.invalidate(getCurrentAccountId(),incidentId);
  const base = ensureBackendUrl();

  const res = await fetchWithTimeout(
    `${base}/api/v1/incidents/${encodeURIComponent(incidentId)}`,
    { method: 'DELETE' },
    options
  );

  return handleResponse<{ success: boolean; id: string; deleted: boolean }>(
    res,
    `/api/v1/incidents/${incidentId}`
  );
}

// ==============================================================================
// DISPATCHES & SINGLE INFERENCE
// ==============================================================================

export interface SendDispatchParams {
  incidentId: string;
  channel?: string;
  destinationReference?: string;
  idempotencyKey?: string;
}

/**
 * Transmit a formal notification dispatch for an incident (POST /api/v1/dispatches/send).
 */
export async function sendDispatch(
  incidentIdOrParams: string | SendDispatchParams,
  channel: string = 'telegram',
  destinationReference?: string,
  idempotencyKey?: string,
  options?: RequestOptions
): Promise<Dispatch> {
  const base = ensureBackendUrl();

  let incidentId: string;
  let targetChannel = channel;
  let destRef = destinationReference;
  let idempKey = idempotencyKey;

  if (typeof incidentIdOrParams === 'object' && incidentIdOrParams !== null) {
    incidentId = incidentIdOrParams.incidentId;
    if (incidentIdOrParams.channel) targetChannel = incidentIdOrParams.channel;
    if (incidentIdOrParams.destinationReference) destRef = incidentIdOrParams.destinationReference;
    if (incidentIdOrParams.idempotencyKey) idempKey = incidentIdOrParams.idempotencyKey;
  } else {
    incidentId = incidentIdOrParams;
  }

  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (idempKey) {
    headers['Idempotency-Key'] = idempKey;
  }

  const res = await fetchWithTimeout(
    `${base}/api/v1/dispatches/send`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify({
        incidentId,
        channel: targetChannel,
        destination_reference: destRef,
        idempotency_key: idempKey,
      }),
    },
    options
  );

  const data = await handleResponse<unknown>(res, '/api/v1/dispatches/send');
  if (!isValidDispatch(data)) {
    throw new ValidationError('Dispatch record failed runtime validation', { data });
  }

  return data;
}

/**
 * Retrieve a dispatch by its unique identifier (GET /api/v1/dispatches/:id).
 */
export async function getDispatch(dispatchId: string, options?: RequestOptions): Promise<Dispatch> {
  const base = ensureBackendUrl();

  const res = await fetchWithTimeout(
    `${base}/api/v1/dispatches/${encodeURIComponent(dispatchId)}`,
    { method: 'GET' },
    options
  );

  const data = await handleResponse<unknown>(res, `/api/v1/dispatches/${dispatchId}`);
  if (!isValidDispatch(data)) {
    throw new ValidationError('Dispatch record failed runtime validation', { data });
  }

  return data;
}

/**
 * Retrieve active dispatch linked to an incident (GET /api/v1/dispatches/incident/:incidentId).
 */
export async function getIncidentDispatch(incidentId: string, options?: RequestOptions): Promise<Dispatch | null> {
  const base = ensureBackendUrl();

  const res = await fetchWithTimeout(
    `${base}/api/v1/dispatches/incident/${encodeURIComponent(incidentId)}`,
    { method: 'GET' },
    options
  );

  const data = await handleResponse<unknown>(res, `/api/v1/dispatches/incident/${incidentId}`);
  if (!data) return null;
  if (!isValidDispatch(data)) {
    throw new ValidationError('Dispatch record failed runtime validation', { data });
  }

  return data;
}

/**
 * Configure operator security PIN (POST /api/v1/dispatches/security/pin).
 */
export async function configurePin(
  pin: string,
  options?: RequestOptions
): Promise<{ success: boolean; message: string }> {
  const base = ensureBackendUrl();

  const res = await fetchWithTimeout(
    `${base}/api/v1/dispatches/security/pin`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin }),
    },
    options
  );

  return handleResponse<{ success: boolean; message: string }>(res, '/api/v1/dispatches/security/pin');
}

/**
 * Revoke/cancel an active dispatch with verified security PIN (POST /api/v1/dispatches/:id/cancel).
 */
export async function cancelDispatch(
  dispatchId: string,
  pin: string,
  options?: RequestOptions
): Promise<CancelDispatchResponse> {
  const base = ensureBackendUrl();

  const res = await fetchWithTimeout(
    `${base}/api/v1/dispatches/${encodeURIComponent(dispatchId)}/cancel`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin }),
    },
    options
  );

  const data = await handleResponse<{ success: boolean; dispatch: unknown; message?: string }>(
    res,
    `/api/v1/dispatches/${dispatchId}/cancel`
  );
  if (!data || typeof data.success !== 'boolean' || !isValidDispatch(data.dispatch)) {
    throw new ValidationError('Invalid cancellation response from backend', { data });
  }

  return { success: data.success, dispatch: data.dispatch, message: data.message };
}

/**
 * Execute single-image neural detection (POST /api/v1/inference/image).
 */
export async function inferSingleImage(
  file: File | Blob,
  targets?: ModelClass[],
  confidenceThreshold?: number,
  options?: RequestOptions
): Promise<SingleImageInferenceResponse> {
  const base = ensureBackendUrl();
  const formData = new FormData();
  formData.append('image', file);
  if (targets && targets.length > 0) {
    formData.append('targets', targets.join(','));
  }
  if (typeof confidenceThreshold === 'number') {
    formData.append('confidence_threshold', String(confidenceThreshold));
  }

  const res = await fetchWithTimeout(
    `${base}/api/v1/inference/image`,
    {
      method: 'POST',
      body: formData,
    },
    options
  );

  const data = await handleResponse<SingleImageInferenceResponse>(res, '/api/v1/inference/image');
  const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
  if (!data || !finite(data.original_width) || data.original_width <= 0
    || !finite(data.original_height) || data.original_height <= 0 || !Array.isArray(data.detections)
    || !data.detections.every(detection =>
      detection && ['person', 'mask', 'knife'].includes(detection.classId)
      && finite(detection.confidence) && detection.confidence >= 0 && detection.confidence <= 1
      && Array.isArray(detection.box) && detection.box.length === 4 && detection.box.every(finite)
      && detection.box[0] >= 0 && detection.box[1] >= 0
      && detection.box[2] > detection.box[0] && detection.box[3] > detection.box[1]
      && detection.box[2] <= data.original_width && detection.box[3] <= data.original_height)) {
    throw new ValidationError('Invalid single image inference response from backend', { data });
  }

  return data;
}

/** Saves a camera frame only after the server analyzes and persists its own predictions. */
export async function saveCameraAlert(image: Blob, targets: ModelClass[], idempotencyKey: string, options?: RequestOptions): Promise<Incident> {
  incidentMemory.invalidate(getCurrentAccountId(),'');
  const request=incidentRequest();
  const body = new FormData();
  body.append('image', image, 'camera.jpg');
  body.append('targets', targets.join(','));
  const response = await fetchWithTimeout(`${ensureBackendUrl()}/api/v1/incidents/from-frame`, {
    method: 'POST', body, headers: { 'Idempotency-Key': idempotencyKey },
  }, options);
  const incident = await handleResponse<unknown>(response, '/api/v1/incidents/from-frame');
  if (!isValidIncident(incident)) throw new ValidationError('Invalid saved camera alert response');
  return rememberIncident(request,incident);
}

/** An explicit operator alert without inventing a camera capture or model result. */
export async function saveManualCameraAlert(key: string, options?: RequestOptions): Promise<Incident> {
  incidentMemory.invalidate(getCurrentAccountId(),'');
  const request=incidentRequest();
  const route = '/api/v1/incidents/manual-camera';
  const res = await fetchWithTimeout(`${ensureBackendUrl()}${route}`, { method: 'POST', headers: { 'Idempotency-Key': key } }, options);
  const incident = await handleResponse<unknown>(res, route);
  if (!isValidIncident(incident)) throw new ValidationError('Invalid manual camera alert response');
  return rememberIncident(request,incident);
}

export async function dismissFalseAlarm(id: string, options?: RequestOptions): Promise<Incident> {
  incidentMemory.invalidate(getCurrentAccountId(),id);
  const request=incidentRequest();
  const route = `/api/v1/incidents/${encodeURIComponent(id)}/false-alarm`;
  const res = await fetchWithTimeout(`${ensureBackendUrl()}${route}`, { method: 'POST' }, options);
  const incident = await handleResponse<unknown>(res, route);
  if (!isValidIncident(incident)) throw new ValidationError('Invalid false alarm response');
  return rememberIncident(request,incident);
}

// Owner action journal: never represents provider delivery or police acknowledgement.
import type { ResponseContacts, SecurityResponse, ResponseKind, Recipient } from './securityResponse.ts';
async function responseRequest<T>(path: string, method = 'GET', body?: unknown, options?: RequestOptions): Promise<T> {
  const url = `${ensureBackendUrl()}/api/v1/incidents${path}`;
  const res = await fetchWithTimeout(url, {method, headers: {'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)}, options);
  return handleResponse<T>(res, url);
}
export const getResponseContacts = (options?: RequestOptions) => responseRequest<ResponseContacts>('/response-contacts', 'GET', undefined, options);
export const saveResponseContacts = (body: ResponseContacts) => responseRequest<ResponseContacts>('/response-contacts', 'PUT', body);
export const getSecurityResponse = (id: string, options?: RequestOptions) => responseRequest<SecurityResponse>(`/${encodeURIComponent(id)}/response`, 'GET', undefined, options);
export const recordSecurityResponse = (id: string, kind: ResponseKind, recipient: Recipient = 'owner', detail = '', eventId: string = crypto.randomUUID()) => {incidentMemory.invalidate(getCurrentAccountId(),id);return responseRequest<SecurityResponse>(`/${encodeURIComponent(id)}/response`, 'POST', {kind,recipient,detail,eventId});};
export async function downloadEvidenceImage(url: string): Promise<Blob> {
  if (url.startsWith('data:image/')) return (await fetch(url)).blob();
  const parsed = new URL(url, window.location.origin);
  if (parsed.origin !== window.location.origin || !parsed.pathname.startsWith('/api/v1/evidence/')) throw new Error('Unsupported evidence URL');
  const res = await fetchWithTimeout(parsed.href);
  if (!res.ok) throw new Error('Evidence could not be downloaded');
  return res.blob();
}

/** Saves the exact inferred camera frame; server verifies mask and caps an episode at 3 photos. */
export async function saveAutomaticEvidence(image: Blob, session: string, time: number, options?: RequestOptions): Promise<Incident> {
  incidentMemory.invalidate(getCurrentAccountId(),'');
  const request=incidentRequest();
  const form=new FormData();form.append('image',image,'automatic-mask.jpg');form.append('session_key',session);form.append('time_seconds',String(time));
  const path='/api/v1/incidents/auto-evidence';
  const res=await fetchWithTimeout(`${ensureBackendUrl()}${path}`,{method:'POST',body:form},{timeoutMs:45000,...options});
  const result=await handleResponse<unknown>(res,path);
  if(!isValidIncident(result))throw new ValidationError('Automatic evidence save returned an invalid incident');
  return rememberIncident(request,result);
}
