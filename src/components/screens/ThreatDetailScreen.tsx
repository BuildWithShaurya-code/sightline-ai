/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { MaterialIcon } from '../common/MaterialIcon.tsx';
import { FalseAlarmSlider } from '../common/FalseAlarmSlider.tsx';
import { BottomNavigation } from '../navigation/BottomNavigation.tsx';
import { ScreenId, Incident, Frame, Detection, IncidentStatus } from '../../types/sightline.ts';
import {pendingIncidentConfirmation,finishIncidentConfirmation} from '../../services/incidentConfirmation.ts';
import { getIncident, getCachedIncident, reviewIncident } from '../../services/api.ts';

interface ThreatDetailScreenProps {
  onBack?: () => void;
  onFalseAlarmCleared?: () => void;
  onNavigate?: (screen: ScreenId, modeOrId?: string) => void;
  latestFrame?: string | null;
  videoUrl?: string | null;
  incidentId?: string | null;
  onIncidentResolved?: (id:string)=>void;
}

export const ThreatDetailScreen: React.FC<ThreatDetailScreenProps> = ({
  onBack,
  onFalseAlarmCleared,
  onNavigate,
  latestFrame,
  videoUrl,
  incidentId,
  onIncidentResolved,
}) => {
  const [activeIncident, setActiveIncident] = useState<Incident | null>(()=>incidentId?(pendingIncidentConfirmation(incidentId)?.incident||getCachedIncident(incidentId)):null);
  const [selectedFrameIndex, setSelectedFrameIndex] = useState<number>(0);
  const [isInspecting, setIsInspecting] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(()=>!incidentId||(!pendingIncidentConfirmation(incidentId)&&!getCachedIncident(incidentId)));
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isReviewing, setIsReviewing] = useState<boolean>(()=>Boolean(pendingIncidentConfirmation(incidentId)));
  const [confirmationError,setConfirmationError]=useState('');
  const [previewOnly,setPreviewOnly]=useState(()=>Boolean(pendingIncidentConfirmation(incidentId)?.previewOnly));
  const resolvedId=useRef<string|null>(null);
  const [confirmedHere, setConfirmedHere] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Bounding box letterbox scaling state
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [containerDims, setContainerDims] = useState<{ width: number; height: number }>({
    width: 0,
    height: 0,
  });
  const [naturalDims, setNaturalDims] = useState<{ width: number; height: number }>({
    width: 640,
    height: 360,
  });

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 3000);
  };

  // Measure container dimensions for responsive bounding box calculations
  const updateContainerDims = useCallback(() => {
    if (containerRef.current) {
      setContainerDims({
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
      });
    }
  }, []);

  useEffect(() => {
    updateContainerDims();
    window.addEventListener('resize', updateContainerDims);
    return () => window.removeEventListener('resize', updateContainerDims);
  }, [updateContainerDims]);

  // Re-measure container dimensions whenever activeIncident changes
  useEffect(() => {
    if (activeIncident) {
      const t = setTimeout(() => {
        updateContainerDims();
      }, 50);
      return () => clearTimeout(t);
    }
  }, [activeIncident, updateContainerDims]);

  // Load only the selected incident and its saved response status.
  const fetchRevision=useRef(0);
  const fetchIncidentData = useCallback(async () => {
    if(incidentId&&resolvedId.current===incidentId)return;
    const revision=++fetchRevision.current;
    const pending=pendingIncidentConfirmation(incidentId);
    setIsLoading(!pending&&(!incidentId||!getCachedIncident(incidentId)));
    setErrorMessage(null);setConfirmationError('');setConfirmedHere(null);
    try {
      if(pending){
        setActiveIncident(pending.incident);setIsLoading(false);setIsReviewing(true);
        try{
          const saved=await pending.result;
          if(revision!==fetchRevision.current)return;
          setActiveIncident(saved);setConfirmedHere(saved.id);setPreviewOnly(false);
          if(pending.previewOnly){resolvedId.current=saved.id;onIncidentResolved?.(saved.id);}
        }catch(e){if(revision===fetchRevision.current)setConfirmationError(e instanceof Error?e.message:'Confirmation was not saved. Retry below.');}
        finally{if(revision===fetchRevision.current)setIsReviewing(false);if(!pending.previewOnly||resolvedId.current)finishIncidentConfirmation(pending);}
      } else {
        const resolved=incidentId?await getIncident(incidentId):null;
        if(revision!==fetchRevision.current)return;
        setActiveIncident(resolved);
        const maskEvidence=resolved?.detections.find(d=>d.classId==='mask')?.evidence_id;
        setSelectedFrameIndex(Math.max(0,resolved?.frames.findIndex(f=>f.id===maskEvidence) ?? 0));
      }
    }catch(err){
      if(revision!==fetchRevision.current)return;
      setErrorMessage(err instanceof Error?err.message:'Could not load incident');setActiveIncident(null);
    }finally{if(revision===fetchRevision.current)setIsLoading(false);}
  },[incidentId,onIncidentResolved]);
  useEffect(()=>{void fetchIncidentData();return()=>{++fetchRevision.current;};},[fetchIncidentData]);

  // Review Incident Action (CONFIRM or DISMISS)
  const handleReview = async (newStatus: IncidentStatus) => {
    if (!activeIncident || isReviewing) return;

    if(newStatus === 'confirmed' && activeIncident.status === 'confirmed'){
      setConfirmedHere(activeIncident.id);showToast('Threat confirmed. You can now contact police or security.');return;
    }
    setIsReviewing(true);setConfirmationError('');
    try {
      const reason =
        newStatus === 'confirmed'
          ? 'Threat confirmed by human operator review'
          : 'Dismissed by human operator review';
      const pending=previewOnly?pendingIncidentConfirmation(incidentId):null;
      const updated=pending?await pending.retry():await reviewIncident(activeIncident.id,newStatus,reason);
      if(pending){setPreviewOnly(false);resolvedId.current=updated.id;onIncidentResolved?.(updated.id);finishIncidentConfirmation(pending);}
      setActiveIncident(updated);
      if(newStatus === 'confirmed')setConfirmedHere(updated.id);
      showToast(`Incident #${updated.id} ${newStatus.toUpperCase()}`);

    } catch (err: unknown) {
      console.error('Review failed:', err);
      const msg = err instanceof Error ? err.message : 'Failed to update review status';
      setConfirmationError(msg);showToast(`Review failed: ${msg}`);
    } finally {
      setIsReviewing(false);
    }
  };

  const openDismissal = async () => { if(activeIncident) onNavigate?.('dismiss-incident',activeIncident.id); };
  const openSecurityResponse = () => {
    if(!activeIncident)return;
    if(activeIncident.status!=='confirmed' || confirmedHere!==activeIncident.id){showToast('First confirm the threat before contacting police or security.');return;}
    onNavigate?.('security-response',activeIncident.id);
  };

  // Active frame & media
  const framesList: Frame[] = activeIncident?.frames || [];
  const activeFrame = framesList[selectedFrameIndex] || null;
  const displayImage = activeFrame?.imageDataUrl || activeIncident?.thumbnail || null;

  const displayZone = activeIncident?.zone || (previewOnly?'Camera preview':'Zone A // Main Perimeter');
  const displaySource = activeIncident?.channel || activeIncident?.sourceId || (videoUrl ? 'Active Session' : 'Not available');

  const formatIncidentTime = (isoString?: string): string => {
    if (!isoString) return 'Not available';
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return isoString;
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return isoString;
    }
  };

  const formatIncidentDate = (isoString?: string): string => {
    if (!isoString) return '';
    try {
      const d = new Date(isoString);
      const now = new Date();
      if (d.toDateString() === now.toDateString()) {
        return 'Today';
      }
      return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
      return '';
    }
  };

  const displayTime = activeIncident
    ? `${formatIncidentDate(activeIncident.createdAt)} ${formatIncidentTime(activeIncident.createdAt)}`
    : 'Not available';

  const getDetectionTheme = (classId: string) => {
    switch (classId) {
      case 'person':
        return {
          bg: 'bg-emerald-950/60',
          border: 'border-emerald-500/70',
          boxBorder: '#4edea3',
          text: 'text-emerald-300',
          icon: 'person',
          label: 'PERSON',
        };
      case 'mask':
        return {
          bg: 'bg-amber-950/60',
          border: 'border-amber-500/70',
          boxBorder: '#f59e0b',
          text: 'text-amber-300',
          icon: 'masks',
          label: 'MASK',
        };
      case 'knife':
        return {
          bg: 'bg-rose-950/60',
          border: 'border-rose-500/70',
          boxBorder: '#f43f5e',
          text: 'text-rose-300',
          icon: 'hardware',
          label: 'KNIFE',
        };
      default:
        return {
          bg: 'bg-slate-900',
          border: 'border-slate-700',
          boxBorder: '#94a3b8',
          text: 'text-slate-300',
          icon: 'warning',
          label: classId.toUpperCase(),
        };
    }
  };

  // Bounding box calculations accounting for object-fit: contain letterboxing
  const renderBoundingBoxes = () => {
    if (!activeIncident || !activeIncident.detections) {
      return null;
    }

    const cW = containerDims.width || containerRef.current?.clientWidth || 398;
    const cH = containerDims.height || containerRef.current?.clientHeight || 298;
    if (cW === 0 || cH === 0) return null;

    const { width: nW, height: nH } = naturalDims;

    const scale = Math.min(cW / nW, cH / nH);
    const displayedW = nW * scale;
    const displayedH = nH * scale;
    const offsetX = (cW - displayedW) / 2;
    const offsetY = (cH - displayedH) / 2;

    // Filter detections for the active frame
    const relevantDetections = activeIncident.detections.filter((det) => {
      if (activeFrame?.id && det.evidence_id) {
        return det.evidence_id === activeFrame.id;
      }
      if (det.video_offset_seconds !== undefined && activeFrame?.timeSeconds !== undefined) {
        return Math.abs(det.video_offset_seconds - activeFrame.timeSeconds) < 0.3;
      }
      if (det.frame_index !== undefined && framesList.length > 1) {
        // Source-video frame numbers are not indices in the selected evidence list.
        return false;
      }
      return true;
    });

    return relevantDetections.map((det: Detection, idx: number) => {
      if (!det.box) return null;
      const [x1, y1, x2, y2] = det.box;
      const left = offsetX + x1 * scale;
      const top = offsetY + y1 * scale;
      const width = (x2 - x1) * scale;
      const height = (y2 - y1) * scale;
      const theme = getDetectionTheme(det.classId);
      const pct = Math.round(det.confidence * 100);

      return (
        <div
          key={`bbox-${idx}`}
          data-testid="bounding-box"
          className="bounding-box-overlay absolute pointer-events-none transition-all duration-150"
          style={{
            left: `${left}px`,
            top: `${top}px`,
            width: `${Math.max(4, width)}px`,
            height: `${Math.max(4, height)}px`,
            border: `2px solid ${theme.boxBorder}`,
            boxShadow: `0 0 10px ${theme.boxBorder}66, inset 0 0 8px ${theme.boxBorder}33`,
          }}
        >
          {/* Tactical Target Tag Badge */}
          <div
            className="absolute left-0 px-1.5 py-0.5 rounded text-[10px] font-mono font-extrabold tracking-wider text-black flex items-center gap-1 shadow-md whitespace-nowrap"
            style={{ backgroundColor: theme.boxBorder, top: top < 20 ? 0 : -20 }}
          >
            <span>{theme.label}</span>
            <span>{pct}%</span>
          </div>

          {/* Corner HUD Reticles */}
          <div className="absolute -top-1 -left-1 w-2 h-2 border-t-2 border-l-2 border-white" />
          <div className="absolute -top-1 -right-1 w-2 h-2 border-t-2 border-r-2 border-white" />
          <div className="absolute -bottom-1 -left-1 w-2 h-2 border-b-2 border-l-2 border-white" />
          <div className="absolute -bottom-1 -right-1 w-2 h-2 border-b-2 border-r-2 border-white" />
        </div>
      );
    });
  };

  return (
    <div className="flex flex-col w-full min-h-screen bg-[#051424] text-[#d4e4fa] pb-24 select-none">
      {/* Top Header */}
      <header className="sticky top-0 z-30 bg-[#051424]/90 backdrop-blur-md px-4 py-3 flex items-center justify-between border-b border-[#273647]/50 shadow-sm">
        <button
          type="button"
          onClick={onBack}
          className="w-10 h-10 min-w-[40px] min-h-[40px] rounded-lg bg-[#1c2b3c] border border-[#273647] flex items-center justify-center text-[#d4e4fa] hover:bg-[#273647] active:scale-95 transition-all cursor-pointer"
          aria-label="Navigate Back"
        >
          <MaterialIcon name="arrow_back" className="text-[20px]" />
        </button>

        <div className="flex flex-col items-center text-center">
          <span className="font-sans text-xs font-bold text-white tracking-wider uppercase">
            THREAT DETAIL &amp; INCIDENT VIEW
          </span>
          <span className="font-mono text-[11px] font-semibold text-[#4edea3] tracking-widest uppercase">
            {previewOnly?'CAPTURED PHOTO · SAVING':activeIncident ? `#${activeIncident.id}` : 'INCIDENT RECORDS'}
          </span>
        </div>

        <button
          type="button"
          onClick={() => onNavigate?.('operator-login')}
          className="w-10 h-10 min-w-[40px] min-h-[40px] rounded-full bg-[#ffdad7] flex items-center justify-center text-[#410004] shadow-sm hover:brightness-105 active:scale-95 transition-all cursor-pointer"
          aria-label="Operator Profile Menu"
        >
          <MaterialIcon name="person" className="text-[20px]" />
        </button>
      </header>

      {/* Main Content Area */}
      <div className="flex flex-col p-4 gap-3.5">
        {/* Loading Skeleton */}
        {isLoading && (
          <div className="p-8 rounded-3xl bg-[#0d1c2d] border border-[#273647] flex flex-col items-center justify-center gap-3">
            <MaterialIcon name="sync" className="text-[28px] text-[#4edea3] animate-spin" />
            <span className="font-mono text-xs text-[#94a3b8]">Fetching authenticated incident records...</span>
          </div>
        )}

        {/* Error State */}
        {errorMessage && !isLoading && (
          <div className="p-4 rounded-2xl bg-red-950/50 border border-red-500/60 flex flex-col gap-2">
            <span className="font-mono text-xs font-bold text-red-200">{errorMessage}</span>
            <button
              type="button"
              onClick={fetchIncidentData}
              className="self-start px-3 py-1.5 rounded-lg bg-red-900/60 border border-red-500/80 font-mono text-xs text-white"
            >
              Retry Connection
            </button>
          </div>
        )}

        {!isLoading && !errorMessage && activeIncident && (
          <>
            {isReviewing&&<p role="status" className="rounded-xl border border-[#4edea3]/25 bg-[#0d1c2d] p-3 text-sm text-[#4edea3]">{previewOnly?'Saving evidence and confirmation… Your captured photo is below. Keep this tab open while it saves.':'Saving confirmation… Your captured evidence is ready below.'}</p>}
            {confirmationError&&<p role="alert" className="rounded-xl border border-red-400/40 bg-red-950/30 p-3 text-sm text-red-200">{confirmationError} Your evidence is still available. Press Confirm threat to retry.</p>}
            {/* Incident Alert Banner */}
            <div className="relative w-full rounded-3xl bg-gradient-to-r from-[#1c2b3c] via-[#122131] to-[#1c2b3c] p-4 text-white shadow-lg border border-[#273647] overflow-hidden">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-2xl bg-[#0d1c2d] border border-[#4edea3]/40 flex items-center justify-center text-[#4edea3] shrink-0 shadow-md">
                  <MaterialIcon name="shield" className="text-[26px]" />
                </div>

                <div className="flex flex-col min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`w-2 h-2 rounded-full ${
                          activeIncident.status === 'confirmed'
                            ? 'bg-red-400 animate-pulse'
                            : activeIncident.status === 'dismissed'
                            ? 'bg-slate-400'
                            : 'bg-amber-400'
                        }`}
                      />
                      <span className="font-mono text-[11px] font-extrabold uppercase tracking-widest text-[#ffdad6]">
                        {previewOnly?'CAPTURED PREVIEW':`INCIDENT ${activeIncident.status.toUpperCase()}`}
                      </span>
                    </div>

                    {/* Review Badge */}
                    <span
                      className={`font-mono text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase ${
                        activeIncident.status === 'confirmed'
                          ? 'bg-red-950/60 border-red-500/60 text-red-300'
                          : activeIncident.status === 'dismissed'
                          ? 'bg-slate-900 border-slate-700 text-slate-400'
                          : 'bg-amber-950/60 border-amber-500/60 text-amber-300'
                      }`}
                    >
                      {previewOnly?'Not saved yet':activeIncident.status}
                    </span>
                  </div>
                  <h2 className="font-sans text-base font-extrabold leading-tight text-white tracking-tight break-words mt-1">
                    {activeIncident.id.startsWith('INC-AUTO-') ? 'Mask detected' : activeIncident.title || activeIncident.sourceId}
                  </h2>
                </div>
              </div>

              {/* Operator Verification Control Bar */}
              <div className="mt-3 pt-3 border-t border-white/10 grid grid-cols-1 items-stretch gap-2">
                <button
                  type="button"
                  disabled={isReviewing || confirmedHere === activeIncident.id || activeIncident.status === 'dismissed'}
                  onClick={() => handleReview('confirmed')}
                  className="w-full min-h-[48px] py-3 px-4 rounded-xl font-sans text-sm font-bold flex items-center justify-center gap-2 text-white bg-gradient-to-r from-[#b91a24] via-[#ed4147] to-[#b91a24] border border-[#ffb4ab]/50 shadow-[0_4px_16px_rgba(255,84,81,0.2)] hover:brightness-110 active:scale-[0.99] transition-all disabled:cursor-default disabled:active:scale-100"
                >
                  <MaterialIcon name="check_circle" className="text-[16px]" />
                  <span>{isReviewing ? 'Confirming…' : activeIncident.status === 'dismissed' ? 'Incident dismissed' : confirmedHere === activeIncident.id ? 'Threat confirmed' : 'Confirm threat'}</span>
                </button>


              </div>

            </div>
            <div className="rounded-full bg-[#0d1c2d] border border-[#273647] px-4 py-3 text-xs text-[#4edea3]">
              Response: {activeIncident.responseStatus || 'Not contacted'}
            </div>

            {/* Live Frame Capture Viewport with Scaled Bounding Boxes */}
            <div className="relative w-full rounded-2xl bg-[#010f1f] border border-[#273647] overflow-hidden shadow-2xl flex flex-col">
              {/* Viewport Top Bar */}
              <div className="px-3 py-2 flex items-center justify-between bg-[#051424]/90 border-b border-[#273647]/50 z-20">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px] font-bold text-white tracking-wider">
                    KEYFRAME EVIDENCE {framesList.length > 0 ? `(${selectedFrameIndex + 1}/${framesList.length})` : ''}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 font-mono text-[11px]">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                  <span className="text-[#d4e4fa] truncate max-w-[190px]">
                    {activeFrame ? `T+${Number(activeFrame.timeSeconds.toFixed(1))}s` : 'KEYFRAME'}
                  </span>
                </div>
              </div>

              {/* Video Frame Canvas / Captured Image with Overlays */}
              <div
                ref={containerRef}
                className={`relative aspect-[4/3] w-full bg-[#0a121d] overflow-hidden flex items-center justify-center transition-transform duration-300 origin-center ${
                  isInspecting ? 'scale-110' : 'scale-100'
                }`}
              >
                {displayImage ? (
                  <img
                    src={displayImage}
                    alt="Captured Threat Frame"
                    onLoad={(e) => {
                      setNaturalDims({
                        width: e.currentTarget.naturalWidth || 640,
                        height: e.currentTarget.naturalHeight || 360,
                      });
                      updateContainerDims();
                    }}
                    className="w-full h-full object-contain"
                  />
                ) : (
                  <div className="flex flex-col items-center justify-center p-6 text-center text-[#94a3b8] font-mono text-xs gap-1.5">
                    <MaterialIcon name="image_not_supported" className="text-[28px] text-[#94a3b8]/60" />
                    <span className="font-bold text-[#d4e4fa]">No frame captured</span>
                    <span className="text-[11px] text-[#e4beba]/70">
                      No evidence photos are available for this incident. New mask detections capture evidence automatically.
                    </span>
                  </div>
                )}

                {/* Scaled Neural Detections Overlays */}
                {renderBoundingBoxes()}

                {/* Corner Reticle HUD Brackets */}
                <div className="absolute inset-2 pointer-events-none flex flex-col justify-between z-10">
                  <div className="flex justify-between">
                    <div className="w-3.5 h-3.5 border-t-2 border-l-2 border-[#4edea3]/50" />
                    <div className="w-3.5 h-3.5 border-t-2 border-r-2 border-[#4edea3]/50" />
                  </div>
                  <div className="flex justify-between">
                    <div className="w-3.5 h-3.5 border-b-2 border-l-2 border-[#4edea3]/50" />
                    <div className="w-3.5 h-3.5 border-b-2 border-r-2 border-[#4edea3]/50" />
                  </div>
                </div>

                {/* Overlay Footer on Media */}
                <div className="absolute bottom-2 inset-x-2 flex items-end justify-between z-20 pointer-events-none">
                  <div className="flex flex-col bg-[#051424]/90 px-2.5 py-1 rounded border border-white/10 backdrop-blur-sm pointer-events-auto shadow-sm max-w-[200px]">
                    <span className="font-mono text-[11px] text-white flex items-center gap-1 font-semibold truncate">
                      <MaterialIcon name="location_on" className="text-[13px] text-[#4edea3]" />
                      {displayZone}
                    </span>
                    <span className="font-mono text-[11px] text-[#e4beba]/80 truncate">
                      Source: {displaySource}
                    </span>
                  </div>

                  {displayImage && (
                    <button
                      type="button"
                      onClick={() => setIsInspecting(!isInspecting)}
                      className="min-h-[40px] px-3 py-1.5 rounded-lg bg-[#1c2b3c]/90 border border-white/20 text-[#d4e4fa] font-mono text-[11px] font-bold flex items-center gap-1 hover:bg-[#273647] active:scale-95 transition-all shadow-md pointer-events-auto cursor-pointer"
                      aria-label={isInspecting ? 'Reset image zoom' : 'Inspect frame closeup'}
                    >
                      <MaterialIcon name="search" className="text-[14px]" />
                      <span>{isInspecting ? 'Reset' : 'Inspect'}</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Multiple Keyframes Thumbnails Selector Strip */}
              {framesList.length > 1 && (
                <div className="px-3 py-2 bg-[#051424]/95 border-t border-[#273647] flex items-center gap-2 overflow-x-auto scrollbar-none">
                  {framesList.map((f, idx) => (
                    <button
                      key={f.id || idx}
                      type="button"
                      onClick={() => setSelectedFrameIndex(idx)}
                      aria-label={`Select frame ${idx + 1} at ${f.timeSeconds} seconds`}
                      className={`relative w-14 h-10 min-h-[40px] rounded-md overflow-hidden border shrink-0 transition-all cursor-pointer ${
                        selectedFrameIndex === idx
                          ? 'border-[#4edea3] ring-2 ring-[#4edea3]/40 scale-105'
                          : 'border-[#273647] opacity-60 hover:opacity-100'
                      }`}
                    >
                      <img src={f.imageDataUrl} alt={`Frame ${idx + 1}`} className="w-full h-full object-cover" />
                      <span className="absolute bottom-0 right-0 px-1 bg-black/80 font-mono text-[11px] text-[#4edea3]">
                        {Math.round(f.timeSeconds)}s
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {/* Telemetry Strip Under Video */}
              <div className="px-3 py-2 bg-[#051424] border-t border-[#273647] flex items-center justify-between">
                <div className="flex items-center gap-1.5 font-mono text-[11px] text-[#94a3b8] truncate">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#4edea3]" />
                  <span className="truncate">
                    YOLOv11 nano: person, mask, knife • Authenticated Backend
                  </span>
                </div>
                <span className="font-mono text-[11px] text-[#4edea3] shrink-0 pl-1 font-bold">
                  {previewOnly?'LOCAL PREVIEW':isReviewing?'SAVING CONFIRMATION':'EVIDENCE SAVED'}
                </span>
              </div>
            </div>

            <div className="w-full pt-1">
              {/* Open the notification screen for this incident. */}
              <button
                type="button"
                disabled={isReviewing||previewOnly}
                onClick={openSecurityResponse}
                className="group relative w-full min-h-[56px] rounded-full bg-gradient-to-r from-[#b91a24] via-[#ed4147] to-[#b91a24] p-1.5 flex items-center justify-between gap-2 text-white font-sans shadow-[0_4px_20px_rgba(255,84,81,0.35)] border border-[#ffb4ab]/50 hover:brightness-110 active:scale-[0.98] transition-all cursor-pointer"
              >
                <span className="w-10 h-10 rounded-full bg-white/15 flex items-center justify-center shrink-0" aria-hidden="true">
                  <MaterialIcon name="campaign" className="text-[21px]" />
                </span>
                <span className="flex-1 min-w-0 text-center text-[11px] sm:text-xs font-extrabold tracking-wide uppercase">
                  NOTIFY POLICE AND SECURITY
                </span>
                <span className="w-10 h-10 rounded-full bg-white/15 flex items-center justify-center shrink-0" aria-hidden="true">
                  <MaterialIcon name="arrow_forward" className="text-[20px]" />
                </span>
              </button>
              <div className="mt-6 pb-3">
                <FalseAlarmSlider onComplete={openDismissal} disabled={isReviewing || previewOnly || activeIncident.status==='dismissed'} />
              </div>
            </div>
          </>
        )}

        {/* Empty State */}
        {!isLoading && !errorMessage && !activeIncident && (
          <div className="p-8 rounded-3xl bg-[#0d1c2d] border border-[#273647] flex flex-col items-center justify-center text-center gap-3">
            <MaterialIcon name="shield_with_heart" className="text-[36px] text-[#4edea3]" />
            <h3 className="font-sans text-sm font-bold text-white">No Incidents Recorded</h3>
            <p className="font-mono text-xs text-[#94a3b8] max-w-[260px]">
              No alerts have been saved for your current operator. Save a camera alert or analyze a video in Detection Studio.
            </p>
            <button
              type="button"
              onClick={() => onNavigate?.('detection-studio')}
              className="mt-2 px-4 py-2 rounded-full bg-[#4edea3] text-slate-950 font-sans text-xs font-bold"
            >
              Open Detection Studio
            </button>
          </div>
        )}
      </div>

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
      <BottomNavigation activeScreen="threat-detail" onNavigate={onNavigate} />
    </div>
  );
};
