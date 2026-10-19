import {maskAlertConfidence, MASK_ALERT_MIN_CONFIDENCE} from '../../services/maskAlerts.ts';
/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { MaterialIcon } from '../common/MaterialIcon.tsx';
import { TacticalHeader } from '../navigation/TacticalHeader.tsx';
import { BottomNavigation } from '../navigation/BottomNavigation.tsx';
import { ScreenId, Frame, Detection, Incident, InputMode } from '../../types/sightline.ts';
import { ModelClass } from '../../constants/classes.ts';
import { useCameraPreview } from '../../hooks/useCameraPreview.ts';
import { useAutomaticEvidence } from '../../hooks/useAutomaticEvidence.ts';
import { useMaskAlerts } from '../../hooks/useMaskAlerts.ts';
import { useFrameDetection } from '../../hooks/useFrameDetection.ts';
import {beginIncidentConfirmation,beginCaptureConfirmation} from '../../services/incidentConfirmation.ts';
import { ThreatWarningActions } from '../common/ThreatWarningActions.tsx';
import { FrameDetectionOverlay } from '../common/FrameDetectionOverlay.tsx';
import {
  uploadVideo,
  saveCameraAlert,
  saveManualCameraAlert,
  startAnalysis,
  getJob,
  cancelJob,
  getIncident,
} from '../../services/api.ts';

const MAX_VIDEO_SIZE_MB = import.meta.env.VITE_CLOUD_UPLOADS === '1' ? 50 : 100;
const MAX_VIDEO_SIZE_BYTES = MAX_VIDEO_SIZE_MB * 1024 * 1024;
const SEEK_TIMEOUT_MS = 5000;

export type StudioUploadState =
  | 'idle'
  | 'file_selected'
  | 'uploading'
  | 'upload_failed'
  | 'uploaded'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled';

interface DetectionStudioScreenProps {
  onNavigate?: (screen: ScreenId, modeOrId?: string) => void;
  onTriggerAlert?: (incidentId?: string) => void;
  onFrameExtracted?: (
    frameUrl: string,
    videoUrl?: string,
    frames?: Frame[],
    videoName?: string
  ) => void;
  videoUrl?: string | null;
  videoName?: string | null;
  onVideoUploaded?: (videoUrl: string, videoName: string, file?: File) => void;
  initialMode?: InputMode;
  selectedFile?: File | null;
  uploadedSourceId?: string | null;
  onSourceReady?: (sourceId: string) => void;
}

export const DetectionStudioScreen: React.FC<DetectionStudioScreenProps> = ({
  onNavigate,
  onTriggerAlert,
  onFrameExtracted,
  videoUrl: propVideoUrl,
  videoName: propVideoName,
  onVideoUploaded,
  initialMode,
  selectedFile,
  uploadedSourceId,
  onSourceReady,
}) => {
  const [zoomLevel, setZoomLevel] = useState<number>(1.0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);

  // Targets strictly matching trained model classes (person, mask, knife)
  const [targets, setTargets] = useState<Record<ModelClass, boolean>>({
    person: true,
    mask: true,
    knife: true,
  });

  // Video and live camera state
  const [videoFile, setVideoFile] = useState<File | null>(selectedFile || null);
  const [videoUrl, setVideoUrl] = useState<string | null>(propVideoUrl || null);
  const [videoName, setVideoName] = useState<string | null>(propVideoName || null);
  const [duration, setDuration] = useState<number>(0);
  const [currentTime, setCurrentTime] = useState<number>(0);

  const [frameAnalysisEnabled, setFrameAnalysisEnabled] = useState(true);
  const [videoDecodeError, setVideoDecodeError] = useState<string | null>(null);

  // Real backend workflow state
  const [uploadState, setUploadState] = useState<StudioUploadState>(uploadedSourceId ? 'uploaded' : 'idle');
  const [sourceId, setSourceId] = useState<string | null>(uploadedSourceId || null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [confirmingThreat,setConfirmingThreat] = useState(false);
  const [confirmationError,setConfirmationError] = useState('');
  const confirmationPending=useRef(false);
  const [isSavingAlert, setIsSavingAlert] = useState(false);
  const saveAlertPendingRef = useRef(false);
  const openAfterAnalysisRef = useRef(false);
  const snapshotKeyRef = useRef<string | null>(null);
  const capturedCameraPhotoRef = useRef<Blob | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [jobProgress, setJobProgress] = useState<number>(0);
  const [jobStage, setJobStage] = useState<string>('');
  const [jobError, setJobError] = useState<string | null>(null);
  const [noDetectionsFound, setNoDetectionsFound] = useState<boolean>(false);

  // Dynamic extracted keyframes state (typed as Frame[])
  const [extractedFrames, setExtractedFrames] = useState<Frame[]>([]);
  const [videoDetections, setVideoDetections] = useState<Detection[]>([]);
  const [savedIncidentId, setSavedIncidentId] = useState<string | null>(null);
  const [isEvidenceExtracted, setIsEvidenceExtracted] = useState<boolean>(false);
  const [isExtractingManual, setIsExtractingManual] = useState<boolean>(false);

  const [shutterFlash, setShutterFlash] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const scrubberTrackRef = useRef<HTMLDivElement | null>(null);
  const camera = useCameraPreview(videoRef);
  const sourceMeta = useRef({videoUrl,videoName});
  sourceMeta.current = {videoUrl,videoName};
  const isLiveCameraActive = camera.active;
  const cameraError = camera.error;
  useEffect(() => {
    if (camera.active) setIsPlaying(true);
    else if (!videoUrl) setIsPlaying(false);
  }, [camera.active, videoUrl]);
  const sourceRevisionRef = useRef(0);
  const pollingIntervalRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const activeTargetCount =
    (targets.person ? 1 : 0) + (targets.mask ? 1 : 0) + (targets.knife ? 1 : 0);

  const formatTime = (sec: number) => {
    if (isNaN(sec) || sec < 0) sec = 0;
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
  };

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 3500);
  };

  const toggleTarget = (key: ModelClass) => {
    setTargets((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleZoom = (delta: number) => {
    setZoomLevel((prev) => Math.min(2.0, Math.max(1.0, +(prev + delta).toFixed(1))));
  };

  const resetZoom = () => {
    setZoomLevel(1.0);
  };

  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current !== null) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }, []);

  const stopLiveCamera = camera.stop;

  // Source change reset: clear evidence drawer, captured frames, latestFrame, filename, and zoom/target state together
  const resetSourceAndEvidence = () => {
    stopLiveCamera();
    stopPolling();
    sourceRevisionRef.current += 1;
    openAfterAnalysisRef.current = false;
    snapshotKeyRef.current = null;
    capturedCameraPhotoRef.current = null;
    setIsSavingAlert(false);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    setExtractedFrames([]);
    setVideoDetections([]);
    setIsEvidenceExtracted(false);
    setSavedIncidentId(null);
    setUploadState('idle');
    setSourceId(null);
    setActiveJobId(null);
    setIsCancelling(false);
    setJobProgress(0);
    setJobStage('');
    setJobError(null);
    setNoDetectionsFound(false);
    setZoomLevel(1.0);
    setTargets({ person: true, mask: true, knife: true });
    setVideoFile(null);
    setVideoUrl(null);
    setVideoName(null);
    setCurrentTime(0);
    setDuration(0);
    setIsPlaying(false);
    setVideoDecodeError(null);
    setFrameAnalysisEnabled(true);
    onFrameExtracted?.('', '', [], '');

    try {
      localStorage.removeItem('sightline_latest_frame');
      localStorage.removeItem('sightline_video_name');
    } catch (e) {
      console.warn(e);
    }
  };

  // Handle prop changes safely
  useEffect(() => {
    if (propVideoUrl !== undefined && propVideoUrl !== videoUrl) {
      setVideoUrl(propVideoUrl);
    }
  }, [propVideoUrl]);

  useEffect(() => {
    if (propVideoName !== undefined && propVideoName !== videoName) {
      setVideoName(propVideoName);
    }
  }, [propVideoName]);

  // App owns shared file URLs; camera hook owns its tracks. Cleanup runs on unmount only.
  useEffect(() => () => {
    sourceRevisionRef.current += 1;
    stopPolling();
    abortControllerRef.current?.abort();
  }, [stopPolling]);

  useEffect(() => {
    if (initialMode === 'upload') {
      const timer = window.setTimeout(() => fileInputRef.current?.click(), 200);
      return () => window.clearTimeout(timer);
    }
    if (initialMode === 'live') startLiveCamera();
  }, [initialMode]);

  // File Upload Handler with Real Backend Upload
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate video format
    const isVideoType =
      file.type.startsWith('video/') ||
      /\.(mp4|mov|webm|avi|mkv|m4v)$/i.test(file.name);

    if (!isVideoType) {
      showToast('Error: Selected file is not a valid video format.');
      setVideoDecodeError('Invalid file format. Please upload a standard video file (MP4, WebM, MOV).');
      return;
    }

    // Size check
    if (file.size > MAX_VIDEO_SIZE_BYTES) {
      const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
      showToast(`Error: File (${sizeMb}MB) exceeds ${MAX_VIDEO_SIZE_MB}MB size limit.`);
      setVideoDecodeError(`File size (${sizeMb}MB) exceeds maximum allowed ${MAX_VIDEO_SIZE_MB}MB.`);
      return;
    }

    resetSourceAndEvidence();
    const revision = sourceRevisionRef.current;
    const controller = new AbortController();
    abortControllerRef.current = controller;
    e.target.value = ''; // Permit selecting the same file again after a failure.

    const newUrl = URL.createObjectURL(file);
    setVideoFile(file);
    setVideoUrl(newUrl);
    setVideoName(file.name);
    setIsPlaying(true);
    setCurrentTime(0);

    onVideoUploaded?.(newUrl, file.name, file);
    onFrameExtracted?.('', newUrl, [], file.name);


    // Step 4: Upload actual bytes to backend
    setUploadState('uploading');
    showToast(`Uploading ${file.name} to forensic vault...`);

    try {
      const uploadResult = await uploadVideo(file, { signal: controller.signal });
      if (revision !== sourceRevisionRef.current) return;
      setSourceId(uploadResult.sourceId);
      onSourceReady?.(uploadResult.sourceId);
      setUploadState('queued');setJobProgress(0);setJobError(null);setNoDetectionsFound(false);
      showToast('Video uploaded. Automatically scanning for threats and evidence…');
      try {
        const job=await startAnalysis(uploadResult.sourceId,['person','mask','knife'],.25,.25,{signal:controller.signal});
        if(revision!==sourceRevisionRef.current)return;
        setActiveJobId(job.jobId);setUploadState('processing');setJobStage('Automatically collecting evidence…');
        beginJobPolling(job.jobId);
      } catch (analysisError) {
        if(revision!==sourceRevisionRef.current)return;
        setUploadState('failed');setJobError(analysisError instanceof Error?analysisError.message:'Automatic analysis could not start. Retry analysis.');
      }
    } catch (err: unknown) {
      if (revision !== sourceRevisionRef.current) return;
      console.error('Video upload failed:', err);
      setUploadState('upload_failed');
      const msg = err instanceof Error ? err.message : 'Upload failed';
      setJobError(msg);
      showToast(`Upload failed: ${msg}`);
    }
  };

  // Start Real Neural Analysis Job
  const handleStartAnalysis = async () => {
    console.log('[STUDIO] handleStartAnalysis invoked! sourceId:', sourceId, 'uploadState:', uploadState, 'videoFile:', videoFile?.name);
    if (!sourceId && !videoFile) {
      console.warn('[STUDIO] handleStartAnalysis aborted: no sourceId and no videoFile');
      showToast('Please upload a video file first');
      return;
    }

    // Ensure at least one target is chosen
    const selectedTargets = (Object.keys(targets) as ModelClass[]).filter((k) => targets[k]);
    console.log('[STUDIO] selectedTargets:', selectedTargets);
    if (selectedTargets.length === 0) {
      showToast('Select at least one threat target (Person, Mask, Knife)');
      return;
    }

    const revision = sourceRevisionRef.current;
    const controller = abortControllerRef.current || new AbortController();
    abortControllerRef.current = controller;
    const options = { signal: controller.signal };
    let activeSource = sourceId;

    // If sourceId is not yet available, attempt upload now
    if (!activeSource && videoFile) {
      setUploadState('uploading');
      showToast('Uploading video before analysis...');
      try {
        const uploadRes = await uploadVideo(videoFile, options);
        if (revision !== sourceRevisionRef.current) return;
        activeSource = uploadRes.sourceId;
        setSourceId(activeSource);
        onSourceReady?.(activeSource);
        setUploadState('uploaded');
      } catch (uploadErr: unknown) {
        if (revision !== sourceRevisionRef.current) return;
        setUploadState('upload_failed');
        const msg = uploadErr instanceof Error ? uploadErr.message : 'Upload failed';
        showToast(`Upload failed: ${msg}`);
        return;
      }
    }

    if (!activeSource) {
      showToast('No valid media source identifier found');
      return;
    }

    setUploadState('queued');
    setJobProgress(0);
    setJobStage('Enqueuing neural analysis...');
    setJobError(null);
    setNoDetectionsFound(false);

    try {
      console.log('[STUDIO] dispatching startAnalysis with source:', activeSource, 'targets:', selectedTargets);
      const analysisJob = await startAnalysis(activeSource, selectedTargets, 0.25, 0.5, options);
      if (revision !== sourceRevisionRef.current) return;
      console.log('[STUDIO] startAnalysis succeeded! returned jobId:', analysisJob.jobId);
      setActiveJobId(analysisJob.jobId);
      setUploadState('processing');
      setJobStage('Analyzing keyframes...');
      showToast(`Neural analysis dispatched (Job #${analysisJob.jobId.slice(0, 8)})`);

      // Begin polling
      beginJobPolling(analysisJob.jobId);
    } catch (err: unknown) {
      if (revision !== sourceRevisionRef.current) return;
      console.error('[STUDIO] Failed to start analysis job:', err);
      setUploadState('failed');
      const msg = err instanceof Error ? err.message : 'Analysis dispatch failed';
      setJobError(msg);
      showToast(`Analysis failed: ${msg}`);
    }
  };

  // Reliable Job Polling
  const beginJobPolling = (jobId: string) => {
    stopPolling();

    const revision = sourceRevisionRef.current;
    const options = { signal: abortControllerRef.current?.signal };
    let inFlight = false;
    pollingIntervalRef.current = window.setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const job = await getJob(jobId, options);
        if (revision !== sourceRevisionRef.current) return;
        const prog = typeof job.progress === 'number' ? job.progress : 0;
        setJobProgress(prog);
        setJobStage(`Processing (${prog}%)`);

        if (job.status === 'completed') {
          stopPolling();
          setUploadState('completed');

          if (job.incidentId) {
            setSavedIncidentId(job.incidentId);
            const openWhenReady = openAfterAnalysisRef.current;
            openAfterAnalysisRef.current = false;
            setIsEvidenceExtracted(true);
            showToast(`Analysis complete. Incident #${job.incidentId} is ready for review.`);

            // Fetch full incident record with evidence frames
            try {
              const incidentData = await getIncident(job.incidentId, options);
              if (revision !== sourceRevisionRef.current) return;
              setVideoDetections(incidentData.detections);
              // Keep a mask warning visible and audible before the owner opens the saved alert.
              if (openWhenReady && !(targets.mask && maskAlertConfidence(incidentData.detections)!==null)) {
                onTriggerAlert?.(job.incidentId);
              }
              if (incidentData.frames && incidentData.frames.length > 0) {
                setExtractedFrames(incidentData.frames);
                onFrameExtracted?.(
                  incidentData.frames[0].imageDataUrl,
                  sourceMeta.current.videoUrl || undefined,
                  incidentData.frames,
                  sourceMeta.current.videoName || ''
                );
              }
            } catch (incErr) {
              console.warn('Failed to fetch full incident details:', incErr);
              if (revision === sourceRevisionRef.current && openWhenReady) onTriggerAlert?.(job.incidentId);
            }
          } else {
            openAfterAnalysisRef.current = false;
            // Completed with 0 threats detected
            setNoDetectionsFound(true);
            setExtractedFrames([]);
            setIsEvidenceExtracted(false);
            setSavedIncidentId(null);
            showToast('Scan complete: No requested targets (Person, Mask, Knife) detected.');
          }
        } else if (job.status === 'failed') {
          stopPolling();
          openAfterAnalysisRef.current = false;
          setUploadState('failed');
          setJobError(job.error || 'Video analysis failed');
          showToast(`Analysis failed: ${job.error || 'Worker error'}`);
        } else if (job.status === 'cancelled') {
          stopPolling();
          setUploadState('cancelled');
          showToast('Analysis job cancelled by operator.');
        }
      } catch (pollErr: unknown) {
        if (revision === sourceRevisionRef.current) console.warn('Job polling request error (will retry):', pollErr);
      } finally {
        inFlight = false;
      }
    }, 500);
  };

  // A cancellation request is not a completed cancellation; keep polling the worker.
  const handleCancelJob = async () => {
    if (!activeJobId || isCancelling) return;
    const revision = sourceRevisionRef.current;
    setIsCancelling(true);
    try {
      const result = await cancelJob(activeJobId, { signal: abortControllerRef.current?.signal });
      if (revision !== sourceRevisionRef.current) return;
      if (result.status === 'cancelled') {
        stopPolling();
        setUploadState('cancelled');
        showToast('Analysis job cancelled.');
      } else {
        setJobStage(result.cancellation_requested ? 'Cancellation requested; waiting for worker…' : 'Checking final job result…');
        showToast(result.message || 'Cancellation requested; checking worker status.');
      }
    } catch (err: unknown) {
      if (revision !== sourceRevisionRef.current) return;
      showToast(`Cancel failed: ${err instanceof Error ? err.message : 'Unable to cancel job'}`);
    } finally {
      if (revision === sourceRevisionRef.current) setIsCancelling(false);
    }
  };

  const startLiveCamera = () => {
    resetSourceAndEvidence();
    void camera.start();
  };

  // Sync video time
  const handleTimeUpdate = () => {
    if (videoRef.current && !isLiveCameraActive) {
      setCurrentTime(videoRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (videoRef.current && !isLiveCameraActive) {
      setDuration(videoRef.current.duration || 0);
      setVideoDecodeError(null);
    }
  };

  const handleVideoError = () => {
    console.error('HTMLVideoElement error encountered.');
    const errorMsg = 'Video decode error: The browser could not decode this video format or codec.';
    setVideoDecodeError(errorMsg);
    showToast(errorMsg);
    setIsPlaying(false);
  };

  const togglePlayPause = () => {
    if (isLiveCameraActive) {
      showToast('Live camera is continuously streaming');
      return;
    }

    if (!videoUrl || !videoRef.current) {
      showToast('No active video loaded to play');
      return;
    }

    if (videoRef.current.paused) {
      videoRef.current
        .play()
        .then(() => {
          setIsPlaying(true);
        })
        .catch((e) => {
          console.warn('Playback error:', e);
        });
    } else {
      videoRef.current.pause();
      setIsPlaying(false);
    }
  };

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!scrubberTrackRef.current || !duration || isLiveCameraActive) return;
    const rect = scrubberTrackRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const pct = Math.max(0, Math.min(1, clickX / rect.width));
    const targetTime = pct * duration;
    if (videoRef.current && videoUrl) {
      videoRef.current.currentTime = targetTime;
    }
    setCurrentTime(targetTime);
  };

  const handleSeekKeyDown = (e: React.KeyboardEvent) => {
    if (!videoRef.current || !videoUrl || isLiveCameraActive || duration <= 0) return;
    const step = 2; // 2 seconds

    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
      e.preventDefault();
      const next = Math.min(duration, currentTime + step);
      videoRef.current.currentTime = next;
      setCurrentTime(next);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
      e.preventDefault();
      const next = Math.max(0, currentTime - step);
      videoRef.current.currentTime = next;
      setCurrentTime(next);
    } else if (e.key === 'Home') {
      e.preventDefault();
      videoRef.current.currentTime = 0;
      setCurrentTime(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      videoRef.current.currentTime = duration;
      setCurrentTime(duration);
    }
  };

  // Freeze the selected camera photo; the alert saves this photo, not a later live frame.
  const captureLiveSnapshot = async () => {
    if (!videoRef.current || videoRef.current.readyState < 2 || !videoRef.current.videoWidth) {
      showToast('Wait for the camera preview before capturing a snapshot.');
      return;
    }
    const revision = sourceRevisionRef.current;
    setShutterFlash(true);
    setTimeout(() => setShutterFlash(false), 300);
    setIsExtractingManual(true);

    try {
      const video = videoRef.current;
      const offscreen = document.createElement('canvas');
      offscreen.width = video.videoWidth || 640;
      offscreen.height = video.videoHeight || 360;
      const ctx = offscreen.getContext('2d');
      if (!ctx) throw new Error('Could not create canvas context');

      ctx.drawImage(video, 0, 0, offscreen.width, offscreen.height);
      const blob = await new Promise<Blob | null>(resolve => offscreen.toBlob(resolve, 'image/jpeg', .9));
      if (!blob) throw new Error('Could not encode the captured photo.');
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(new Error('Could not preview the captured photo.'));
        reader.readAsDataURL(blob);
      });
      if (revision !== sourceRevisionRef.current) return;
      capturedCameraPhotoRef.current = blob;
      snapshotKeyRef.current = null;
      setSavedIncidentId(null);
      setVideoDetections([]);

      const singleFrame: Frame = {
        id: `manual-${Date.now()}`,
        timeSeconds: 0,
        imageDataUrl: dataUrl,
      };

      setExtractedFrames([singleFrame]);
      setIsEvidenceExtracted(true);
      showToast('Photo captured. Trigger Threat Alert to save this photo as evidence.');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Unable to capture evidence.');
    } finally {
      setIsExtractingManual(false);
    }
  };

  const handleOpenAlert = async () => {
    if (savedIncidentId) {
      onNavigate?.('threat-detail', savedIncidentId);
      return;
    }
    if (!isLiveCameraActive) {
      if (!videoFile && !sourceId) { showToast('Open a camera or upload a video first.'); return; }
      openAfterAnalysisRef.current = true;
      await handleStartAnalysis();
      return;
    }
    if (saveAlertPendingRef.current) return;
    const blob = capturedCameraPhotoRef.current;
    const selected = (['person', 'mask', 'knife'] as ModelClass[]).filter(target => targets[target]);
    if (!selected.length) { showToast('Select a detection target before saving.'); return; }
    saveAlertPendingRef.current = true;
    setIsSavingAlert(true);
    const revision = sourceRevisionRef.current;
    const controller = new AbortController();
    abortControllerRef.current = controller;
    try {
      if (revision !== sourceRevisionRef.current) return;
      snapshotKeyRef.current ||= crypto.randomUUID();
      const incident = blob
        ? await saveCameraAlert(blob, selected, snapshotKeyRef.current, { signal: controller.signal })
        : await saveManualCameraAlert(snapshotKeyRef.current, { signal: controller.signal });
      if (revision !== sourceRevisionRef.current) return;
      setSavedIncidentId(incident.id);
      setVideoDetections(incident.detections);
      setExtractedFrames(incident.frames);
      showToast('Camera alert saved to your history. Operator review is required.');
      onNavigate?.('threat-detail', incident.id);
    } catch (err) {
      if (revision === sourceRevisionRef.current) showToast(err instanceof Error ? err.message : 'Alert could not be saved.');
    } finally {
      saveAlertPendingRef.current = false;
      if (revision === sourceRevisionRef.current) setIsSavingAlert(false);
    }
  };

  const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0;
  const isVideoLoaded = Boolean(videoUrl || isLiveCameraActive);
  const isProcessing = uploadState === 'queued' || uploadState === 'processing';
  const selectedTargetKey = (['person', 'mask', 'knife'] as ModelClass[]).filter(target => targets[target]).join(',');
  const frameDetector = useFrameDetection(
    videoRef,
    isLiveCameraActive ? 'camera' : videoUrl,
    frameAnalysisEnabled && isVideoLoaded && !isProcessing && uploadState !== 'uploading' && !videoDecodeError,
    isLiveCameraActive,
    selectedTargetKey,
  );
  const frameResult = frameDetector.prediction?.response;
  const autoEvidence = useAutomaticEvidence(frameDetector.prediction,isLiveCameraActive ? `camera:${sourceRevisionRef.current}` : null,isLiveCameraActive && targets.mask);
  useEffect(()=>{
    if(autoEvidence.incident){setSavedIncidentId(autoEvidence.incident.id);setExtractedFrames(autoEvidence.incident.frames);setVideoDetections(autoEvidence.incident.detections);}
  },[autoEvidence.incident]);
  const maskAlerts = useMaskAlerts(
    frameDetector.prediction,
    isLiveCameraActive ? `camera:${sourceRevisionRef.current}` : videoUrl,
    isVideoLoaded && targets.mask && !videoDecodeError,
    uploadState === 'completed' ? videoDetections : undefined,
  );

  const confirmDetectedThreat = () => {
    if(confirmationPending.current)return;
    confirmationPending.current=true;
    setConfirmingThreat(true);setConfirmationError('');
    try {
      const task=savedIncidentId?beginIncidentConfirmation(savedIncidentId,autoEvidence.incident):beginCaptureConfirmation(autoEvidence.transfer());
      autoEvidence.freeze();maskAlerts.silence();
      onNavigate?.('threat-detail',task.routeId);
    } catch(e){
      setConfirmationError(e instanceof Error?e.message:'The threat could not be opened. Please retry.');
      confirmationPending.current=false;setConfirmingThreat(false);
    }
  };


  return (
    <div className="flex flex-col w-full min-h-screen bg-[#051424] text-[#d4e4fa] pb-24 select-none">
      {/* Top Header */}
      <TacticalHeader
        isBackendConnected={frameDetector.status !== 'error'}
        rightBadge={frameDetector.error ? 'API ERROR' : isLiveCameraActive ? (frameAnalysisEnabled && selectedTargetKey ? 'LIVE AI' : 'CAMERA') : isVideoLoaded ? 'PLAYBACK' : 'IDLE'}
        onProfileClick={() => onNavigate?.('operator-login')}
      />

      {/* Hidden File Input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="video/*,.mp4,.mov,.webm,.avi,.mkv,.m4v"
        onChange={handleFileUpload}
        className="hidden"
        aria-hidden="true"
      />

      {/* Main Studio Viewport */}
      <div className="flex flex-col p-4 pt-20 gap-3.5">
        {/* Title Row */}
        <div className="flex items-center justify-between px-0.5">
          <h1 className="font-sans text-xl font-bold tracking-tight text-white">
            Forensic Detection Studio
          </h1>
          <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-[#0d1c2d] border border-[#273647]">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                isProcessing
                  ? 'bg-amber-400 animate-ping'
                  : isVideoLoaded
                  ? 'bg-[#4edea3] animate-pulse'
                  : 'bg-[#94a3b8]'
              }`}
            />
            <span className="font-mono text-[11px] font-bold text-[#d4e4fa]">
              {isProcessing
                ? 'SCANNING'
                : uploadState === 'uploading'
                ? 'UPLOADING'
                : isVideoLoaded
                ? 'SOURCE READY'
                : 'STANDBY'}
            </span>
          </div>
        </div>

        {/* Video Canvas Container */}
        <div className={`relative w-full ${isVideoLoaded ? 'aspect-[4/3] shadow-2xl' : 'min-h-[220px]'} rounded-2xl bg-[#010f1f] border border-[#273647] overflow-hidden flex flex-col justify-between`}>
          {/* Active Video Player with Zoom Canvas */}
          <div
            className="absolute inset-0 transition-transform duration-300 origin-center ease-out flex items-center justify-center bg-black"
            style={{ transform: `scale(${zoomLevel})` }}
          >
            {isVideoLoaded ? (
              <video
                ref={videoRef}
                src={!isLiveCameraActive && videoUrl ? videoUrl : undefined}
                playsInline
                autoPlay
                loop={!isLiveCameraActive}
                muted
                onPlaying={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onLoadedMetadata={handleLoadedMetadata}
                onTimeUpdate={handleTimeUpdate}
                onError={handleVideoError}
                className="w-full h-full object-contain"
              />
            ) : (
              <div className="relative w-full h-full flex flex-col items-center justify-center bg-[#010f1f] text-center p-6 gap-2">
                <div className="w-12 h-12 rounded-2xl bg-[#0d1c2d] border border-[#273647] flex items-center justify-center text-[#94a3b8]">
                  <MaterialIcon name="videocam_off" className="text-[28px]" />
                </div>
                <span className="font-mono text-xs font-bold text-white tracking-wider">
                  {camera.pending ? 'OPENING CAMERA…' : 'Choose your video source'}
                </span>
                <span className="font-mono text-[11px] text-[#e4beba]/70 max-w-[240px] leading-relaxed">
                  {camera.pending ? 'Allow camera access in your browser. You can cancel below.' : 'Upload a video or select Live Camera below to begin.'}
                </span>
                {videoDecodeError && (
                  <div className="mt-1 px-3 py-1.5 rounded-lg bg-red-950/50 border border-red-500/50 text-red-200 font-mono text-[11px] max-w-[260px] leading-tight">
                    {videoDecodeError}
                  </div>
                )}
              </div>
            )}
            {isVideoLoaded && frameResult && <FrameDetectionOverlay result={frameResult} />}
          </div>

          {/* Tactical Shutter Flash */}
          {shutterFlash && (
            <div className="absolute inset-0 bg-white pointer-events-none z-30 transition-opacity duration-300 opacity-90 animate-pulse" />
          )}

          {isVideoLoaded && <>
          {/* Corner Reticle HUD Accents */}
          <div className="absolute inset-0 pointer-events-none p-2.5 flex flex-col justify-between z-20">
            <div className="w-full flex justify-between items-start">
              <div className="w-3.5 h-3.5 border-t-2 border-l-2 border-[#4edea3]/70" />
              <div className="w-3.5 h-3.5 border-t-2 border-r-2 border-[#4edea3]/70" />
            </div>
            <div className="w-full flex justify-between items-end pb-10">
              <div className="w-3.5 h-3.5 border-b-2 border-l-2 border-[#4edea3]/70" />
              <div className="w-3.5 h-3.5 border-b-2 border-r-2 border-[#4edea3]/70" />
            </div>
          </div>

          {/* Status & Zoom Toolset Banner */}
          <div className="absolute top-2.5 inset-x-2.5 flex flex-wrap items-center justify-between gap-1.5 z-20 pointer-events-none">
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#010f1f]/90 border border-white/10 backdrop-blur-md shadow-sm max-w-[170px] xs:max-w-[220px]">
              <span
                className={`w-2 h-2 rounded-full shrink-0 ${
                  isLiveCameraActive
                    ? 'bg-amber-400 animate-pulse'
                    : isVideoLoaded
                    ? 'bg-[#4edea3] animate-pulse'
                    : 'bg-[#94a3b8]'
                }`}
              />
              <span className="font-mono text-[11px] text-[#d4e4fa] truncate font-bold">
                {isLiveCameraActive
                  ? 'LIVE CAMERA // AI'
                  : videoName
                  ? `FILE // ${videoName}`
                  : 'STANDBY // NO SOURCE'}
              </span>
            </div>

            {/* Forensic Optical Zoom Toolset */}
            <div className="flex items-center gap-1 p-0.5 rounded-full bg-[#010f1f]/90 border border-white/10 backdrop-blur-md shadow-sm pointer-events-auto">
              <button
                type="button"
                onClick={() => handleZoom(-0.5)}
                className="w-7 h-7 min-w-[28px] min-h-[28px] rounded-full bg-[#1c2b3c]/80 hover:bg-[#4edea3]/20 flex items-center justify-center text-[#d4e4fa] active:scale-95 transition-all cursor-pointer"
                aria-label="Zoom Out"
                title="Zoom Out"
              >
                <MaterialIcon name="remove" className="text-[13px]" />
              </button>
              <span className="font-mono text-[11px] text-[#4edea3] font-bold px-1 min-w-[28px] text-center">
                {zoomLevel.toFixed(1)}x
              </span>
              <button
                type="button"
                onClick={() => handleZoom(0.5)}
                className="w-7 h-7 min-w-[28px] min-h-[28px] rounded-full bg-[#1c2b3c]/80 hover:bg-[#4edea3]/20 flex items-center justify-center text-[#d4e4fa] active:scale-95 transition-all cursor-pointer"
                aria-label="Zoom In"
                title="Zoom In"
              >
                <MaterialIcon name="add" className="text-[13px]" />
              </button>
              <div className="w-[1px] h-3 bg-white/20 mx-0.5" />
              <button
                type="button"
                onClick={resetZoom}
                className="w-7 h-7 min-w-[28px] min-h-[28px] rounded-full bg-[#1c2b3c]/80 hover:bg-[#4edea3]/20 flex items-center justify-center text-[#4edea3] active:scale-95 transition-all cursor-pointer"
                aria-label="Reset zoom reticle"
                title="Reset Reticle"
              >
                <MaterialIcon name="center_focus_weak" className="text-[13px]" />
              </button>
            </div>
          </div>

          </>}
          {/* Playback controls apply only to uploaded videos. */}
          {isVideoLoaded && !isLiveCameraActive && <div className="absolute bottom-0 inset-x-0 z-20 bg-gradient-to-t from-[#010f1f] via-[#010f1f]/95 to-transparent pt-3 pb-2 px-3 flex flex-col gap-1.5 border-t border-white/5 backdrop-blur-[2px]">
            <div className="flex items-center justify-between font-mono text-[11px] text-[#e4beba]/80">
              <div className="flex items-center gap-1.5">
                <span className="text-[#4edea3] font-bold">
                  {formatTime(currentTime)} / {formatTime(duration)}
                </span>
                <span className="text-white/30">•</span>
                <span className="text-white/70">
                  {isLiveCameraActive
                    ? (frameDetector.error ? 'ANALYSIS ERROR' : !selectedTargetKey ? 'NO TARGETS' : frameAnalysisEnabled ? 'LIVE ANALYSIS' : 'ANALYSIS PAUSED')
                    : isVideoLoaded
                    ? isPlaying
                      ? 'PLAYING'
                      : 'PAUSED'
                    : 'NO_SOURCE'}
                </span>
              </div>
              <div className="flex items-center gap-1 text-[11px] text-[#4edea3]">
                <span className="w-1.5 h-1.5 rounded-full bg-[#4edea3] inline-block" />
                <span className="font-bold">
                  {isLiveCameraActive ? 'SAMPLED FRAMES' : isVideoLoaded ? 'VIDEO SYNCED' : 'STANDBY'}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={togglePlayPause}
                disabled={!isVideoLoaded || isLiveCameraActive}
                aria-label={isPlaying ? 'Pause video playback' : 'Start video playback'}
                className={`w-9 h-9 min-w-[36px] min-h-[36px] rounded-full border flex items-center justify-center transition-all shrink-0 ${
                  isVideoLoaded
                    ? 'bg-[#4edea3]/15 border-[#4edea3]/30 text-[#4edea3] hover:bg-[#4edea3]/30 cursor-pointer active:scale-95'
                    : 'bg-[#1c2b3c] border-[#273647] text-[#94a3b8] opacity-50 cursor-not-allowed'
                }`}
              >
                <MaterialIcon
                  name={isPlaying ? 'pause' : 'play_arrow'}
                  className="text-[16px]"
                />
              </button>

              <div
                ref={scrubberTrackRef}
                role="slider"
                tabIndex={isVideoLoaded && !isLiveCameraActive ? 0 : -1}
                aria-label="Video playback progress"
                aria-valuemin={0}
                aria-valuemax={Math.round(duration)}
                aria-valuenow={Math.round(currentTime)}
                aria-valuetext={`${formatTime(currentTime)} of ${formatTime(duration)}`}
                onKeyDown={handleSeekKeyDown}
                onClick={handleSeek}
                className={`relative flex-1 h-5 flex items-center ${
                  isVideoLoaded && !isLiveCameraActive ? 'cursor-pointer group' : 'cursor-not-allowed'
                }`}
              >
                <div className="w-full h-1.5 bg-[#273647] rounded-full overflow-hidden relative">
                  <div
                    className="h-full bg-[#4edea3] shadow-[0_0_8px_rgba(78,222,163,0.8)] transition-all duration-75"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
                <div
                  className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3.5 h-3.5 rounded-full bg-[#4edea3] ring-2 ring-[#010f1f] shadow-[0_0_8px_rgba(78,222,163,1)] pointer-events-none transition-all duration-75"
                  style={{ left: `${progressPercent}%` }}
                />
              </div>
            </div>
          </div>}
        </div>

        {/* Dual Source Selection Buttons */}
        <div className="grid grid-cols-2 gap-3 w-full">
          {/* Button 1: Upload Video */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="group flex items-center justify-center gap-2 min-h-[44px] py-2.5 px-3 rounded-full bg-gradient-to-r from-[#1c2b3c] via-[#122131] to-[#1c2b3c] text-[#4edea3] border border-[#4edea3]/60 shadow-[0_0_15px_rgba(78,222,163,0.22)] hover:shadow-[0_0_22px_rgba(78,222,163,0.4)] active:scale-[0.97] transition-all overflow-hidden cursor-pointer"
          >
            <div className="w-6 h-6 rounded-full bg-[#4edea3]/15 flex items-center justify-center text-[#4edea3] shadow-sm shrink-0">
              <MaterialIcon name="cloud_upload" className="text-[16px]" />
            </div>
            <span className="font-sans text-xs font-bold text-white tracking-tight">
              {uploadState === 'uploading' ? 'Uploading...' : 'Upload Video'}
            </span>
          </button>

          {/* Button 2: Live Camera Feed */}
          <button
            type="button"
            onClick={isLiveCameraActive || camera.pending ? stopLiveCamera : startLiveCamera}
            className={`group flex items-center justify-center gap-2 min-h-[44px] py-2.5 px-3 rounded-full bg-gradient-to-r from-[#1c2b3c] via-[#122131] to-[#1c2b3c] text-white border active:scale-[0.97] transition-all overflow-hidden cursor-pointer ${
              isLiveCameraActive
                ? 'border-amber-400 shadow-[0_0_16px_rgba(251,191,36,0.35)]'
                : 'border-[#273647] hover:border-[#4edea3]/60 shadow-[0_2px_10px_rgba(0,0,0,0.3)]'
            }`}
          >
            <div className="relative flex items-center justify-center shrink-0">
              <MaterialIcon
                name="videocam"
                className={`text-[18px] ${isLiveCameraActive ? 'text-amber-300' : 'text-[#94a3b8]'}`}
              />
              {isLiveCameraActive && (
                <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-amber-400 animate-ping" />
              )}
            </div>
            <span className="font-sans text-xs font-bold text-white tracking-tight">
              {camera.pending ? 'Cancel Camera' : isLiveCameraActive ? 'Stop Camera' : 'Live Camera'}
            </span>
          </button>
        </div>

        <section aria-label="Mask alert settings" className="rounded-xl border border-[#273647] bg-[#0d1c2d] p-3 flex flex-col gap-2 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-semibold text-[#4edea3]">Mask alerts {targets.mask ? 'on' : 'off'} · {maskAlerts.audio.playing ? 'SIREN PLAYING' : maskAlerts.audio.ready ? 'Siren ready' : 'Sound needs permission'}</span>
            {!maskAlerts.audio.ready && <button type="button" onClick={() => void maskAlerts.enable()} className="min-h-[40px] px-3 rounded-lg border border-[#4edea3]/50 text-[#4edea3]">Enable siren</button>}
          </div>
          {maskAlerts.permission === 'default' && <button type="button" onClick={() => void maskAlerts.requestNotifications()} className="self-start min-h-[40px] px-3 rounded-lg border border-[#273647] text-white">Enable desktop notifications</button>}
          <p className="text-[11px] text-[#94a3b8]">{maskAlerts.permission === 'granted' ? 'Desktop notifications enabled.' : maskAlerts.permission === 'denied' ? 'Desktop notifications blocked in browser settings. On-screen alerts remain active.' : maskAlerts.permission === 'unsupported' ? 'This browser supports on-screen alerts; desktop notifications are unavailable.' : 'On-screen alerts are active. Desktop notifications are optional.'} Mask notifications and the siren trigger only at {Math.round(MASK_ALERT_MIN_CONFIDENCE*100)}% mask confidence or above. Lower-confidence predictions can still appear in the results. Review each warning; model predictions can be wrong.</p>
          {maskAlerts.audio.error && <p className="text-amber-200">{maskAlerts.audio.error}</p>}
          {maskAlerts.notificationError && <p className="text-amber-200">{maskAlerts.notificationError}</p>}
        </section>

        {cameraError && (
          <section role="alert" aria-label="Camera access help" className="p-3 rounded-xl bg-red-950/40 border border-red-500/50 text-red-100 text-xs flex flex-col gap-3">
            <p>{cameraError}</p>
            <button
              type="button"
              onClick={camera.previewBlocked ? () => void camera.resumePreview() : startLiveCamera}
              className="self-start min-h-[44px] rounded-full px-4 py-2 bg-[#1c2b3c] border border-white/30 font-bold text-white hover:bg-[#273647] cursor-pointer"
            >
              {camera.previewBlocked ? 'Resume Camera Preview' : 'Retry Live Camera'}
            </button>
          </section>
        )}

        {isVideoLoaded && (
          <section aria-label="Frame analysis status" className="p-3 rounded-xl bg-[#0d1c2d] border border-[#4edea3]/40 text-xs flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-[#4edea3]">
                {isProcessing ? 'Full video analysis running' : !selectedTargetKey ? 'Choose a detection target' : !frameAnalysisEnabled ? 'Frame analysis paused' : frameDetector.status === 'error' ? 'Frame analysis unavailable' : frameDetector.status === 'waiting' ? 'Waiting for video frames…' : frameDetector.status === 'analyzing' ? 'Analyzing frame…' : frameResult ? 'Model predictions' : 'Waiting for the next frame…'}
              </span>
              {!isLiveCameraActive && <button type="button" disabled={isProcessing} onClick={() => setFrameAnalysisEnabled(previous => !previous)} className="min-h-[36px] px-3 rounded-full border border-[#273647] text-white disabled:opacity-40">
                {frameAnalysisEnabled ? 'Pause Frame Analysis' : 'Resume Frame Analysis'}
              </button>}
            </div>
            {frameDetector.error && (
              <div role="alert" className="text-red-200 flex flex-col gap-2">
                <span>{frameDetector.error}</span>
                <button type="button" onClick={frameDetector.retry} className="min-h-[40px] rounded-lg border border-red-400 px-3 self-start">Retry Frame Analysis</button>
              </div>
            )}
            {frameResult && (
              <div className="flex flex-wrap gap-2" aria-label="Latest frame predictions">
                {frameResult.detections.length === 0 ? <span>No selected targets detected in this frame.</span> : frameResult.detections.map((detection, index) => (
                  <span key={`${detection.classId}-${index}`} className="font-mono px-2 py-1 rounded bg-[#122131] text-white">{detection.classId.toUpperCase()} {Math.round(detection.confidence * 100)}%</span>
                ))}
              </div>
            )}
            <p className="text-[11px] text-[#94a3b8] leading-relaxed">
              {isLiveCameraActive ? 'Camera frames are analyzed on this backend about once per second.' : 'Uploaded footage is analyzed automatically and matching evidence photos are saved.'} Minimum confidence: 25%. Predictions need review; a mask prediction is not proof of theft. Mask predictions at {Math.round(MASK_ALERT_MIN_CONFIDENCE*100)}% confidence or above can trigger an on-screen warning and siren. Mask evidence is captured automatically. Confirm Threat opens your saved evidence immediately. Your confirmation is saved before response actions become available.
            </p>
          </section>
        )}

        {/* Target Threat Matrix Section */}
        <div className="flex flex-col gap-2 p-3 rounded-2xl bg-[#0d1c2d] border border-[#273647] shadow-md">
          <div className="flex items-center justify-between border-b border-[#273647] pb-1.5">
            <span className="font-sans font-semibold text-[11px] text-[#d4e4fa] uppercase tracking-wider">
              TARGET THREAT MATRIX
            </span>
            <span className="font-mono text-[11px] text-[#4edea3] bg-[#4edea3]/10 px-2 py-0.5 rounded-full border border-[#4edea3]/25 font-bold">
              {activeTargetCount}/3 ACTIVE
            </span>
          </div>

          <div className="grid grid-cols-3 gap-2 pt-1">
            {/* Person Pill */}
            <button
              type="button"
              aria-pressed={targets.person}
              onClick={() => toggleTarget('person')}
              className={`flex items-center justify-center gap-1.5 min-h-[40px] py-2 px-2 rounded-full bg-[#0d1c2d] border border-[#4edea3]/40 text-[#4edea3] shadow-[0_0_8px_rgba(78,222,163,0.15)] transition-all cursor-pointer ${
                targets.person ? 'opacity-100 ring-1 ring-[#4edea3]/30' : 'opacity-40'
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-[#4edea3] shrink-0" />
              <span className="font-mono text-[11px] font-semibold break-words">Person</span>
            </button>

            {/* Mask Pill */}
            <button
              type="button"
              aria-pressed={targets.mask}
              onClick={() => toggleTarget('mask')}
              className={`flex items-center justify-center gap-1.5 min-h-[40px] py-2 px-2 rounded-full bg-[#0d1c2d] border border-[#ffb95f]/40 text-[#ffb95f] shadow-[0_0_8px_rgba(255,185,95,0.15)] transition-all cursor-pointer ${
                targets.mask ? 'opacity-100 ring-1 ring-[#ffb95f]/30' : 'opacity-40'
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-[#ffb95f] shrink-0" />
              <span className="font-mono text-[11px] font-semibold break-words">Mask</span>
            </button>

            {/* Knife Pill */}
            <button
              type="button"
              aria-pressed={targets.knife}
              onClick={() => toggleTarget('knife')}
              className={`flex items-center justify-center gap-1.5 min-h-[40px] py-2 px-2 rounded-full bg-[#0d1c2d] border border-[#ca8100]/40 text-[#ffddb8] shadow-[0_0_8px_rgba(202,129,0,0.15)] transition-all cursor-pointer ${
                targets.knife ? 'opacity-100 ring-1 ring-[#ca8100]/30' : 'opacity-40'
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-[#ca8100] shrink-0" />
              <span className="font-mono text-[11px] font-semibold break-words">Knife</span>
            </button>
          </div>
        </div>

        {/* Real Neural Analysis Action Bar */}
        <div className="w-full flex flex-col gap-2">
          {/* Progress bar when queued/processing */}
          {isProcessing && (
            <div className="w-full p-3 rounded-2xl bg-[#0d1c2d] border border-amber-500/50 flex flex-col gap-2 shadow-lg">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-amber-300 font-bold flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
                  {jobStage.toUpperCase()}
                </span>
                <span className="text-white font-bold">{jobProgress}%</span>
              </div>
              <div className="w-full h-2 bg-[#1c2b3c] rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-amber-500 to-[#4edea3] transition-all duration-300"
                  style={{ width: `${jobProgress}%` }}
                />
              </div>
            </div>
          )}

          {/* Honest No-Detections Banner */}
          {noDetectionsFound && (
            <div className="p-3.5 rounded-2xl bg-[#0d1c2d] border border-slate-700 text-slate-300 font-mono text-xs flex items-center justify-between shadow-md">
              <div className="flex items-center gap-2">
                <MaterialIcon name="verified" className="text-[18px] text-[#4edea3]" />
                <span>Scan complete: No requested targets (Person, Mask, Knife) detected.</span>
              </div>
            </div>
          )}

          {/* Job Error Banner */}
          {jobError && (
            <div className="p-3 rounded-2xl bg-red-950/50 border border-red-500/60 text-red-200 font-mono text-xs flex items-center gap-2">
              <MaterialIcon name="error" className="text-[18px] text-red-400 shrink-0" />
              <span>{jobError}</span>
            </div>
          )}

          {/* Action Row */}
          <div className="w-full flex items-center gap-2">
            {isLiveCameraActive ? (
              <div className="flex-1 min-h-[50px] py-3 px-4 rounded-2xl bg-[#1c2b3c] border border-amber-500/50 text-amber-300 font-sans text-xs font-bold flex items-center justify-center gap-2 shadow-md" role="status">
                <MaterialIcon name="photo_camera" className="text-[18px]" />
                <span>{autoEvidence.saving?'Saving automatic evidence…':autoEvidence.incident?`Automatic evidence: ${autoEvidence.incident.frames.length}/3 photos`:'Evidence photos capture automatically when a mask is detected'}</span>
              </div>
            ) : (
              <button
                type="button"
                onClick={handleStartAnalysis}
                disabled={!isVideoLoaded || isProcessing || uploadState === 'uploading'}
                aria-label="Start backend neural analysis"
                className={`hero-evidence-pulse group relative flex-1 min-h-[52px] py-3 px-3.5 rounded-2xl backdrop-blur-md border flex items-center justify-between gap-2 shadow-[0_4px_22px_rgba(0,0,0,0.3)] transition-all overflow-hidden ${
                  isVideoLoaded && !isProcessing && uploadState !== 'uploading'
                    ? 'bg-[#122131]/80 border-[#4edea3]/40 hover:border-[#4edea3]/70 active:scale-[0.98] cursor-pointer'
                    : 'bg-[#122131]/40 border-[#273647] opacity-50 cursor-not-allowed'
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0 flex-1 text-left">
                  <div
                    className={`w-10 h-10 rounded-xl border flex items-center justify-center shrink-0 shadow-sm ${
                      isVideoLoaded
                        ? 'bg-[#4edea3]/10 border-[#4edea3]/25 text-[#4edea3]'
                        : 'bg-[#1c2b3c] border-[#273647] text-[#94a3b8]'
                    }`}
                  >
                    <MaterialIcon name="psychology" className="text-[20px]" />
                  </div>
                  <div className="flex flex-col text-left min-w-0">
                    <span className="font-sans text-xs sm:text-sm font-bold text-white tracking-wide truncate">
                      {uploadState === 'uploading'
                        ? 'Uploading Video to Vault...'
                        : isProcessing
                        ? `Scanning (${jobProgress}%)...`
                        : isVideoLoaded
                        ? 'Run Neural Threat Analysis'
                        : 'Load Video to Analyze'}
                    </span>
                    <span className="font-mono text-[11px] text-[#94a3b8] truncate">
                      {isVideoLoaded
                        ? 'Dispatches YOLOv11 worker job'
                        : 'Video source required'}
                    </span>
                  </div>
                </div>
                <div
                  className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg border font-mono text-[11px] font-semibold tracking-wider shrink-0 ${
                    isVideoLoaded
                      ? 'bg-[#4edea3]/15 border-[#4edea3]/30 text-[#4edea3]'
                      : 'bg-[#1c2b3c] border-[#273647] text-[#94a3b8]'
                  }`}
                >
                  <MaterialIcon name="auto_awesome" className="text-[14px]" />
                  <span>{isProcessing ? 'SCANNING' : 'ANALYZE'}</span>
                </div>
              </button>
            )}

            {isProcessing && (
              <button
                type="button"
                onClick={handleCancelJob}
                disabled={isCancelling}
                className="min-h-[52px] py-3 px-4 rounded-2xl bg-red-950/60 border border-red-500/60 text-red-300 font-mono text-xs font-bold active:scale-95 transition-all cursor-pointer"
                title="Cancel running analysis job"
              >
                Cancel
              </button>
            )}
          </div>
        </div>

        {/* Dynamic Evidence Drawer (from real backend incident frames) */}
        {isEvidenceExtracted && extractedFrames.length > 0 && (
          <div className="flex flex-col gap-2.5 p-3 rounded-2xl bg-[#0d1c2d] border border-[#4edea3]/40 shadow-xl ring-1 ring-[#4edea3]/20">
            <div className="flex items-center justify-between border-b border-[#273647] pb-2">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-md bg-[#4edea3]/20 flex items-center justify-center text-[#4edea3]">
                  <MaterialIcon name="folder_special" className="text-[16px]" />
                </div>
                <div className="flex flex-col text-left">
                  <span className="font-sans text-[12px] font-bold text-white leading-tight">
                    Evidence Keyframes ({extractedFrames.length})
                  </span>
                  <span className="font-mono text-[11px] text-[#94a3b8]">
                    {savedIncidentId ? `Incident: #${savedIncidentId}` : 'Preview Frame'}
                  </span>
                </div>
              </div>
              <span className="font-mono text-[11px] px-2 py-0.5 rounded-full bg-[#1c2b3c] text-[#4edea3] border border-[#4edea3]/40 font-bold flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-[#4edea3]" />
                {savedIncidentId ? 'SAVED' : 'LOCAL ONLY'}
              </span>
            </div>

            {savedIncidentId && videoDetections.length > 0 && (
              <div aria-label="Saved video predictions" className="flex flex-wrap gap-2 text-[11px] font-mono">
                {(['person', 'mask', 'knife'] as ModelClass[]).map(target => {
                  const matches = videoDetections.filter(detection => detection.classId === target);
                  return matches.length > 0 ? <span key={target} className="px-2 py-1 rounded bg-[#122131] text-white">{target.toUpperCase()} {Math.round(Math.max(...matches.map(detection => detection.confidence)) * 100)}% · {matches.length} prediction(s)</span> : null;
                })}
              </div>
            )}

            {/* Horizontal Thumbnails Strip */}
            <div className="overflow-x-auto flex gap-2.5 pb-1 scrollbar-none">
              {extractedFrames.map((frame, i) => (
                <div
                  key={frame.id || i}
                  className="shrink-0 w-36 rounded-xl bg-[#122131] border border-[#273647] overflow-hidden flex flex-col shadow-md"
                >
                  <div className="relative aspect-[4/3] w-full bg-[#010f1f] overflow-hidden flex items-center justify-center">
                    <img
                      src={frame.imageDataUrl}
                      alt={`Extracted keyframe ${i + 1}`}
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute top-1 left-1 px-1.5 py-0.5 rounded bg-black/85 font-mono text-[11px] text-white flex items-center gap-1">
                      <span className="w-1 h-1 rounded-full bg-[#4edea3]" />
                      {formatTime(frame.timeSeconds)}
                    </div>
                  </div>
                  <div className="p-1.5 flex flex-col bg-[#122131]">
                    <span className="font-sans text-xs font-bold text-white truncate">
                      Frame {i + 1}
                    </span>
                    <span className="font-mono text-[11px] text-[#4edea3] truncate">
                      {savedIncidentId ? 'Detection candidate' : 'Unanalyzed'}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Actions Row */}
            <div className="grid grid-cols-2 gap-2.5 pt-1">
              <button
                type="button"
                disabled={!savedIncidentId}
                onClick={() => savedIncidentId && onNavigate?.('threat-detail', savedIncidentId)}
                className="min-h-[44px] flex items-center justify-center gap-2 py-2.5 px-3 rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 text-slate-950 font-sans text-xs font-extrabold shadow-md active:scale-95 transition-all cursor-pointer"
              >
                <MaterialIcon name="visibility" className="text-[16px]" />
                <span>View Threat Detail</span>
              </button>
              <button
                type="button"
                onClick={() => setIsEvidenceExtracted(false)}
                className="min-h-[44px] flex items-center justify-center gap-2 py-2.5 px-3 rounded-full bg-rose-950/40 border border-rose-500/40 text-rose-300 font-sans text-xs font-bold active:scale-95 transition-all cursor-pointer"
              >
                <MaterialIcon name="close" className="text-[16px]" />
                <span>Close Drawer</span>
              </button>
            </div>
          </div>
        )}

        {/* Bottom Tactical Action Buttons */}
        <div className="flex flex-col gap-3 pt-1">
          {/* Pause / Resume Video Playback */}
          {isVideoLoaded && !isLiveCameraActive && <button
            type="button"
            onClick={togglePlayPause}
            disabled={!isVideoLoaded}
            className={`w-full min-h-[48px] py-2.5 px-5 rounded-full font-sans text-xs font-bold flex items-center justify-center gap-2.5 shadow-md active:scale-[0.98] transition-all border ${
              !isVideoLoaded
                ? 'bg-[#1c2b3c] text-[#94a3b8] border-[#273647] opacity-50 cursor-not-allowed'
                : isPlaying
                ? 'bg-[#1c2b3c] text-[#d4e4fa] border-[#4edea3]/40 cursor-pointer'
                : 'bg-[#4edea3] text-[#003824] border-[#6ffbbe] shadow-[0_4px_16px_rgba(78,222,163,0.35)] cursor-pointer'
            }`}
          >
            <div className="w-6 h-6 rounded-full bg-black/15 flex items-center justify-center">
              <MaterialIcon
                name={isPlaying ? 'pause' : 'play_arrow'}
                className="text-[18px]"
              />
            </div>
            <span>
              {isPlaying ? 'Pause Video Playback' : 'Resume Video Playback'}
            </span>
          </button>}

          {/* Trigger Threat Alert Button */}
          <button
            type="button"
            onClick={handleOpenAlert}
            disabled={isSavingAlert || isExtractingManual || isProcessing || uploadState === 'uploading' || !isVideoLoaded || activeTargetCount === 0}
            className="w-full min-h-[50px] py-2.5 px-5 rounded-full bg-gradient-to-r from-[#b91a24] via-[#ff5451] to-[#b91a24] text-white font-sans text-xs font-extrabold flex items-center justify-center gap-2.5 shadow-[0_4px_20px_rgba(255,84,81,0.5)] border border-[#ffdad6]/40 active:scale-95 transition-all tracking-wide ring-2 ring-[#ffb4ab]/30 cursor-pointer"
          >
            <div className="w-7 h-7 rounded-full bg-white/20 flex items-center justify-center shadow-inner">
              <MaterialIcon name="warning" className="text-[18px] text-white" />
            </div>
            <span>{isSavingAlert ? 'SAVING CAMERA ALERT…' : savedIncidentId ? 'OPEN SAVED ALERT' : isLiveCameraActive ? 'TRIGGER THREAT ALERT' : 'ANALYZE VIDEO & SAVE ALERT'}</span>
          </button>
        </div>
      </div>

      {maskAlerts.warning && <section role="alert" aria-label="Threat detected alert" className="fixed z-50 top-20 left-1/2 -translate-x-1/2 w-[calc(100%-2rem)] max-w-[398px] rounded-2xl border-2 border-[#ff5451] bg-[#36131d] p-4 shadow-[0_0_35px_rgba(255,84,81,0.35)] text-white">
        <div className="flex items-start gap-3"><MaterialIcon name="warning" className="text-[28px] text-[#ff9a97]"/><div><h2 className="font-bold text-lg">THREAT DETECTED</h2><p className="text-sm">{Math.round(maskAlerts.warning.confidence*100)}% confidence · {maskAlerts.warning.time}</p></div></div>
        <p className="text-xs mt-2 text-[#f4c5c3]">Review the camera or video. This prediction is not confirmation of theft.</p>
        <ThreatWarningActions opening={confirmingThreat} incidentReady={Boolean(savedIncidentId)||autoEvidence.canConfirm} onReview={()=>void confirmDetectedThreat()} onDismiss={maskAlerts.dismiss}/>
        <p className="text-xs mt-2 text-[#f4c5c3]">{savedIncidentId?'Confirm to open the evidence.':autoEvidence.canConfirm?'Confirm to open your captured photo now. Upload continues in the background.':isProcessing?'Video analysis is preparing the alert.':'Preparing a camera photo…'}</p>
        {(autoEvidence.error || confirmationError) && <div role="alert" className="mt-2 text-xs text-amber-200">{autoEvidence.error || confirmationError}{autoEvidence.error && <button className="block underline min-h-[40px]" onClick={autoEvidence.retry}>Retry evidence save</button>}</div>}
      </section>}

      {/* Accessible Toast Notification */}
      {toastMessage && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-20 inset-x-4 flex justify-center z-50 pointer-events-none"
        >
          <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-[#1c2b3c]/95 border border-[#4edea3]/50 text-white font-mono text-xs shadow-2xl backdrop-blur-md">
            <MaterialIcon name="check" className="text-[#4edea3] text-[16px]" />
            <span>{toastMessage}</span>
          </div>
        </div>
      )}

      {/* Bottom Navigation */}
      <BottomNavigation activeScreen="detection-studio" onNavigate={onNavigate} />
    </div>
  );
};
