/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect } from 'react';
import { MaterialIcon } from '../common/MaterialIcon.tsx';
import { TacticalHeader } from '../navigation/TacticalHeader.tsx';
import { BottomNavigation } from '../navigation/BottomNavigation.tsx';
import { ScreenId, Incident } from '../../types/sightline.ts';
import { MODEL_CLASSES } from '../../constants/classes.ts';
import { checkHealthReady, getModelCapabilities, listIncidents, getCachedIncidents } from '../../services/api.ts';
import {useSecuritySetup} from '../../hooks/useSecuritySetup.ts';
import {securitySetupComplete} from '../../services/securitySetup.ts';
import {SystemStatusCard,DashboardSecuritySetup,LatestIncidentCard} from '../dashboard/DashboardCards.tsx';

interface DashboardScreenProps {
  onNavigate?: (screen: ScreenId, modeOrId?: string) => void;
  videoUrl?: string | null;
  videoName?: string | null;
  latestFrame?: string | null;
  onVideoUploaded?: (videoUrl: string, videoName: string, file?: File) => void;
}

export const DashboardScreen: React.FC<DashboardScreenProps> = ({
  onNavigate,
  videoUrl,
  videoName,
}) => {
  const setup=useSecuritySetup();
  const [setupLater,setSetupLater]=useState(false);
  const [activeVideo, setActiveVideo] = useState<string | null>(videoUrl || null);
  const [activeName, setActiveName] = useState<string | null>(videoName || null);
  const [latestIncident, setLatestIncident] = useState<Incident | null>(()=>getCachedIncidents({page:1,page_size:1})?.items[0]||null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [incidentsLoading,setIncidentsLoading]=useState(()=>!getCachedIncidents({page:1,page_size:1}));
  const [incidentsError,setIncidentsError]=useState(false);
  const [checkedAt,setCheckedAt]=useState<Date|null>(null);
  const [supportedTargets, setSupportedTargets] = useState<string[]>([...MODEL_CLASSES]);

  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    if (videoUrl !== undefined) {
      setActiveVideo(videoUrl);
    }
  }, [videoUrl]);

  useEffect(() => {setActiveName(videoName || null);}, [videoName]);

  // Load readiness, capabilities, and real latest incident from backend
  useEffect(() => {
    let isMounted = true;

    const controller=new AbortController();
    async function loadBackendData() {
      // No dependency between these requests. Render each result as soon as it arrives.
      void checkHealthReady({signal:controller.signal}).then(health=>{
        if(isMounted){setIsConnected(health.status==='ready');setCheckedAt(new Date());}
      }).catch(()=>{if(isMounted){setIsConnected(false);setCheckedAt(new Date());}})
        .finally(()=>{if(isMounted)setIsLoading(false);});
      void getModelCapabilities({signal:controller.signal}).then(caps=>{
        if(isMounted&&caps.supported_classes?.length)setSupportedTargets(caps.supported_classes);
      }).catch(()=>{/* Keep the declared supported classes while the API is unavailable. */});
      void listIncidents({page:1,page_size:1},{signal:controller.signal}).then(result=>{
        if(isMounted)setLatestIncident(result.items[0]||null);
      }).catch(()=>{if(isMounted){setLatestIncident(null);setIncidentsError(true);}})
        .finally(()=>{if(isMounted)setIncidentsLoading(false);});
    }

    loadBackendData();
    const timer=setInterval(()=>{if(document.hidden)return;void checkHealthReady().then(health=>{if(isMounted){setIsConnected(health.status==='ready');setCheckedAt(new Date());}}).catch(()=>{if(isMounted){setIsConnected(false);setCheckedAt(new Date());}});},20000);
    return () => {
      isMounted = false;controller.abort();clearInterval(timer);
    };
  }, []);


  return (
    <div className="flex flex-col w-full min-h-screen bg-[#051424] text-[#d4e4fa] pb-24 select-none">
      {/* Top Header */}
      <TacticalHeader
        isBackendConnected={isConnected}
        isCheckingConnection={isLoading}
        onProfileClick={() => onNavigate?.('operator-login')}
        onLogout={() => onNavigate?.('operator-login')}
      />

      {/* Main Container */}
      <div className="flex flex-col p-4 pt-20 gap-3.5">
        <SystemStatusCard ready={isConnected} checking={isLoading} checkedAt={checkedAt}/>
        <DashboardSecuritySetup complete={securitySetupComplete(setup.details)} loading={setup.loading} error={setup.error} later={setupLater} onLater={()=>setSetupLater(true)} onOpen={()=>onNavigate?.('security-setup')}/>

        {/* Target Active Pills Row strictly matching verified targets */}
        <div className="grid grid-cols-3 gap-2">
          {supportedTargets.map((target) => {
            const isPerson = target === 'person';
            const isMask = target === 'mask';
            const colorClass = isPerson
              ? 'border-[#4edea3]/40 text-[#4edea3]'
              : isMask
              ? 'border-[#ffb95f]/40 text-[#ffb95f]'
              : 'border-[#ff5449]/40 text-[#ff5449]';
            const dotClass = isPerson ? 'bg-[#4edea3]' : isMask ? 'bg-[#ffb95f]' : 'bg-[#ff5449]';

            return (
              <div
                key={target}
                className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-full bg-[#0d1c2d] border ${colorClass} shadow-sm`}
              >
                <span className={`w-2 h-2 rounded-full ${dotClass}`} />
                <span className="font-sans text-[11px] font-medium truncate capitalize">
                  {target}
                </span>
              </div>
            );
          })}
        </div>

        {/* Central Tactical Radar Scope Button */}
        <button
          type="button"
          onClick={() => onNavigate?.('detection-studio')}
          className="relative w-full aspect-square max-h-[260px] rounded-3xl bg-[#010f1f] border border-[#4edea3]/30 shadow-[0_0_30px_rgba(78,222,163,0.15)] hover:border-[#4edea3]/60 hover:shadow-[0_0_35px_rgba(78,222,163,0.25)] flex flex-col items-center justify-center overflow-hidden my-1 cursor-pointer transition-all active:scale-[0.99] outline-none"
          aria-label="Launch AI Detection Studio"
        >
          {/* Subtle tactical grid background */}
          <div
            className="absolute inset-0 opacity-20 pointer-events-none"
            style={{
              backgroundImage: 'radial-gradient(#4edea3 1px, transparent 1px)',
              backgroundSize: '20px 20px',
            }}
          />

          {/* Concentric Radar Rings & Crosshairs */}
          <div className="absolute w-52 h-52 rounded-full border border-[#4edea3]/20 flex items-center justify-center pointer-events-none">
            <div className="w-36 h-36 rounded-full border border-[#4edea3]/25 flex items-center justify-center">
              <div className="w-20 h-20 rounded-full border border-[#4edea3]/30" />
            </div>
            <div className="absolute inset-0 rounded-full radar-sweep pointer-events-none" />
          </div>

          {/* Crosshair HUD lines */}
          <div className="absolute inset-x-8 top-1/2 h-[1px] bg-[#4edea3]/20 pointer-events-none" />
          <div className="absolute inset-y-8 left-1/2 w-[1px] bg-[#4edea3]/20 pointer-events-none" />

          {/* Center Target Box */}
          <div className="relative z-10 flex flex-col items-center text-center p-4 pointer-events-none">
            <div className="w-10 h-10 rounded-xl bg-[#1c2b3c]/80 border border-[#4edea3]/50 flex items-center justify-center text-[#4edea3] mb-2 shadow-[0_0_15px_rgba(78,222,163,0.3)]">
              <MaterialIcon name="radar" className="text-[24px]" />
            </div>
            <h2 className="font-sans text-2xl font-extrabold tracking-wider text-white">
              DETECT
            </h2>
            <span className="font-mono text-[11px] font-bold tracking-widest text-[#4edea3] mt-0.5">
              {isLoading?'OPEN WORKSPACE':isConnected?'READY TO SCAN':'OPEN WORKSPACE'}
            </span>
          </div>
        </button>

        {/* Status Pills Below Radar */}
        <div className="grid grid-cols-2 gap-2">
          <div className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-full bg-[#0d1c2d] border border-[#273647] shadow-sm min-h-[40px]">
            <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-[#4edea3]' : 'bg-amber-400'}`} />
            <span className="font-mono text-[11px] font-bold text-[#d4e4fa]">
              {isLoading?'Checking engine…':isConnected ? 'YOLO11 nano' : 'Engine offline'}
            </span>
          </div>

          <div className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-full bg-[#0d1c2d] border border-[#ffb95f]/30 shadow-sm min-h-[40px]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#ffb95f]" />
            <span className="font-mono text-[11px] font-bold text-[#d4e4fa] truncate">
              {supportedTargets.length} detection classes
            </span>
          </div>
        </div>

        {/* Section: CHOOSE INPUT MODE */}
        <div className="flex flex-col gap-2 pt-1">
          <div className="flex items-center justify-between px-0.5">
            <span className="font-sans text-sm font-semibold text-[#d4e4fa]">
              Start detection
            </span>
            <span className="font-mono text-[11px] font-bold text-[#4edea3] bg-[#0d1c2d] px-2 py-0.5 rounded-full border border-[#4edea3]/30">
              YOLOv11 NANO
            </span>
          </div>

          {/* Option 1: Upload Video */}
          <button
            type="button"
            onClick={() => onNavigate?.('detection-studio', 'upload')}
            className="w-full p-3.5 rounded-2xl bg-[#0d1c2d] hover:bg-[#122131] border border-[#273647] hover:border-[#4edea3]/50 flex items-center justify-between shadow-md active:scale-[0.98] transition-all cursor-pointer min-h-[44px]"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#4edea3]/10 border border-[#4edea3]/30 flex items-center justify-center text-[#4edea3]">
                <MaterialIcon name="note_add" className="text-[20px]" />
              </div>
              <div className="flex flex-col text-left gap-1 min-w-0"><span className="font-sans text-sm font-semibold text-white">Upload a video</span><span className="text-xs text-[#94a3b8]">Review recorded footage</span></div>
            </div>
            <div className="w-8 h-8 rounded-full bg-[#1c2b3c] flex items-center justify-center text-[#d4e4fa]">
              <MaterialIcon name="arrow_forward" className="text-[16px]" />
            </div>
          </button>

          {/* Option 2: Live Camera (Explicit Phase 6 Status) */}
          <button
            type="button"
            onClick={() => onNavigate?.('detection-studio', 'live')}
            className="w-full p-3.5 rounded-2xl bg-[#0d1c2d] hover:bg-[#122131] border border-[#273647] flex items-center justify-between shadow-md active:scale-[0.98] transition-all cursor-pointer min-h-[44px]"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#1c2b3c] border border-[#273647] flex items-center justify-center text-[#94a3b8]">
                <MaterialIcon name="videocam" className="text-[20px]" />
              </div>
              <div className="flex flex-col text-left">
                <span className="font-sans text-xs font-bold text-white">
                  Start live camera
                </span>
                <span className="font-sans text-xs text-[#94a3b8]">
                  Open the camera workspace
                </span>
              </div>
            </div>
            <div className="w-8 h-8 rounded-full bg-[#1c2b3c] flex items-center justify-center text-[#d4e4fa]">
              <MaterialIcon name="arrow_forward" className="text-[16px]" />
            </div>
          </button>
        </div>

        {/* Section: LATEST MODEL DETECTION RESULT */}
        <div className="flex flex-col gap-2 pt-1">
          <div className="flex items-center justify-between px-0.5">
            <span className="font-sans text-sm font-semibold text-[#d4e4fa]">
              Latest alert
            </span>
            {latestIncident && (
              <span className="font-mono text-[11px] font-bold text-[#d4e4fa] bg-[#1c2b3c] px-2 py-0.5 rounded border border-[#273647]">
                {latestIncident.status==='confirmed'?'Confirmed':latestIncident.status==='dismissed'?'Dismissed':'Needs review'}
              </span>
            )}
          </div>

          {latestIncident ? (
            <LatestIncidentCard incident={latestIncident} onOpen={()=>onNavigate?.('threat-detail',latestIncident.id)}/>
          ) : (
            <div className="w-full rounded-2xl bg-[#0d1c2d] border border-[#273647] p-5 flex flex-col items-center justify-center text-center gap-1.5 shadow-md">
              <MaterialIcon name="verified_user" className="text-[28px] text-[#4edea3]/60 mb-0.5" />
              <span className="font-sans text-xs font-bold text-white">
                {incidentsLoading?'Loading latest alert…':incidentsError?'Alerts unavailable':'No alerts yet'}
              </span>
              <span className="font-sans text-xs text-[#94a3b8] max-w-[260px]">
                {incidentsLoading?'Other tools are ready to open.':incidentsError?'Open History to retry loading your alerts.':'Start a camera or upload footage to review model predictions.'}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Navigation */}
      <BottomNavigation
        activeScreen="dashboard"
        onNavigate={(screen) => onNavigate?.(screen)}
      />

    </div>
  );
};
