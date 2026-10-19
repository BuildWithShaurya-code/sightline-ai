/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { ScreenId, InputMode, Frame } from './types/sightline.ts';
import { MaterialIcon } from './components/common/MaterialIcon.tsx';
import { OperatorLoginScreen } from './components/screens/OperatorLoginScreen.tsx';
import { DismissIncidentScreen } from './components/screens/DismissIncidentScreen.tsx';
import { ThreatDetailScreen } from './components/screens/ThreatDetailScreen.tsx';
import { DashboardScreen } from './components/screens/DashboardScreen.tsx';
import { SecuritySetupScreen } from './components/screens/SecuritySetupScreen.tsx';
import { SecurityResponseScreen } from './components/screens/SecurityResponseScreen.tsx';
import { DetectionStudioScreen } from './components/screens/DetectionStudioScreen.tsx';
import { HistoryLogsScreen } from './components/screens/HistoryLogsScreen.tsx';
import { isAuthenticated, logout, restoreSession, onAuthStateChange, getCurrentAccountId } from './services/auth.ts';
import {clearIncidentConfirmation,pendingIncidentConfirmation} from './services/incidentConfirmation.ts';
import {clearIncidentMemory} from './services/api.ts';
import { enableSiren, stopSiren } from './services/maskAlerts.ts';

export default function App() {
  // Unlock Web Audio during an actual click/key action, before async camera startup.
  useEffect(() => {
    const arm = () => { void enableSiren(); };
    window.addEventListener('pointerdown', arm);
    window.addEventListener('keydown', arm);
    return () => { window.removeEventListener('pointerdown',arm); window.removeEventListener('keydown',arm); stopSiren(); };
  }, []);

  const [isSessionLoading, setIsSessionLoading] = useState<boolean>(true);
  const [setupNotice,setSetupNotice]=useState('');
  useEffect(()=>{if(!setupNotice)return;const timer=setTimeout(()=>setSetupNotice(''),5000);return()=>clearTimeout(timer);},[setupNotice]);
  const [currentScreen, setCurrentScreen] = useState<ScreenId>('operator-login');
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [latestFrame, setLatestFrame] = useState<string | null>(null);
  const [activeVideoUrl, setActiveVideoUrl] = useState<string | null>(null);
  const [activeVideoFile, setActiveVideoFile] = useState<File | null>(null);
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null);
  const [activeVideoName, setActiveVideoName] = useState<string | null>(null);
  const [accountKey,setAccountKey]=useState<string|null>(null);
  const accountRef=useRef<string|null>(null);
  const [extractedFrames, setExtractedFrames] = useState<Frame[]>([]);
  const [studioMode, setStudioMode] = useState<InputMode | undefined>(undefined);

  // Shared playback must survive navigation between Dashboard and Studio.
  useEffect(() => () => {
    if (activeVideoUrl?.startsWith('blob:')) URL.revokeObjectURL(activeVideoUrl);
  }, [activeVideoUrl]);

  // Authentication gate & parameterized hash route parser
  const handleRouteSync = useCallback(() => {
    const rawHash = window.location.hash.replace(/^#\/?/, '');
    const segments = rawHash.split('/');
    const route = segments[0] || '';
    const paramId = segments[1] || null;

    const authenticated = isAuthenticated();

    // Map route aliases
    let targetScreen: ScreenId | null = null;
    const targetId: string | null = paramId;

    if (route === 'alerts' || route === 'threat-detail') {
      targetScreen = 'threat-detail';
    } else if (route === 'account-settings') {
      // Retired screen: old bookmarks lead to the account's security setup.
      targetScreen = 'security-setup';
      window.location.hash = '#/security-setup';
    } else if (route === 'security-setup') {
      targetScreen = 'security-setup';
    } else if (route === 'dismiss-incident') {
      targetScreen = 'dismiss-incident';
    } else if (route === 'security-response' || route === 'dispatch' || route === 'dispatch-receipt') {
      targetScreen = 'security-response';
    } else if (route === 'dashboard') {
      targetScreen = 'dashboard';
    } else if (route === 'detection-studio' || route === 'studio') {
      targetScreen = 'detection-studio';
    } else if (route === 'history-logs' || route === 'history') {
      targetScreen = 'history-logs';
    } else if (route === 'operator-login' || route === 'login') {
      targetScreen = 'operator-login';
    } else if (!route) {
      targetScreen = authenticated ? 'dashboard' : 'operator-login';
    }

    // Gating: If unauthenticated, redirect all protected routes to login
    if (!authenticated) {
      if (targetScreen !== 'operator-login') {
        setCurrentScreen('operator-login');
        window.location.hash = '#/operator-login';
        return;
      }
      setCurrentScreen('operator-login');
      return;
    }

    // A full reload cannot restore a browser-only, not-yet-saved photo.
    if(targetScreen==='threat-detail'&&paramId?.startsWith('PENDING-')&&!pendingIncidentConfirmation(paramId)){
      setCurrentScreen('history-logs');setSelectedIncidentId(null);window.location.hash='#/history-logs';
      setSetupNotice('Check History to see whether your capture finished saving.');return;
    }

    // Authenticated user trying to access login redirects to dashboard
    if (targetScreen === 'operator-login') {
      targetScreen = 'security-setup';
      window.location.hash = '#/security-setup';
    }

    if (targetScreen) {
      // Input actions are one-time choices, not part of browser back/forward navigation.
      if (targetScreen !== 'detection-studio') setStudioMode(undefined);
      setCurrentScreen(targetScreen);
      setSelectedIncidentId(targetId);
    }
  }, []);

  // Initialize and verify session on initial mount
  useEffect(() => {
    const syncAccount = () => {
      const id=getCurrentAccountId();
      if(id!==accountRef.current){
        clearIncidentMemory();clearIncidentConfirmation();
        accountRef.current=id;setAccountKey(id);
        setSelectedIncidentId(null);setActiveVideoUrl(null);setActiveVideoFile(null);setActiveSourceId(null);setActiveVideoName(null);setLatestFrame(null);setExtractedFrames([]);setStudioMode(undefined);setSetupNotice('');
        stopSiren();
        try{for(const key of ['sightline_video_name','sightline_latest_frame'])localStorage.removeItem(key);}catch{/* Legacy browser capture data is never displayed. */}
      }
    };
    const initSession = async () => {
      try {
        await restoreSession();
      } finally {
        syncAccount();
        setIsSessionLoading(false);
        handleRouteSync();
      }
    };

    initSession();
    const unsubscribe = onAuthStateChange(loggedIn => {
      const changed=getCurrentAccountId()!==accountRef.current;
      syncAccount();
      if(changed)window.location.hash=loggedIn?'#/security-setup':'#/operator-login';
      if(changed||!loggedIn)handleRouteSync();
    });
    window.addEventListener('hashchange', handleRouteSync);
    return () => {unsubscribe(); window.removeEventListener('hashchange', handleRouteSync);};
  }, [handleRouteSync]);

  const resolveIncident=useCallback((id:string)=>{setSelectedIncidentId(id);window.history.replaceState(null,'',`#/threat-detail/${encodeURIComponent(id)}`);},[]);

  const navigateTo = (screen: ScreenId, modeOrId?: string) => {
    if (screen === 'threat-detail') {
      if (modeOrId) {
        setSelectedIncidentId(modeOrId);
        window.location.hash = `#/threat-detail/${modeOrId}`;
      } else {
        setSelectedIncidentId(null);
        window.location.hash = '#/threat-detail';
      }
      setCurrentScreen('threat-detail');
      return;
    }

    if (screen === 'security-setup') {
      setSelectedIncidentId(modeOrId || null);
      window.location.hash=modeOrId?`#/security-setup/${modeOrId}`:'#/security-setup';
      setCurrentScreen('security-setup');return;
    }

    if (screen === 'dismiss-incident') {
      setSelectedIncidentId(modeOrId || null);
      window.location.hash = modeOrId ? `#/dismiss-incident/${modeOrId}` : '#/dismiss-incident';
      setCurrentScreen('dismiss-incident');
      return;
    }

    if (screen === 'security-response' || screen === 'dispatch-receipt') {
      if (modeOrId) {
        setSelectedIncidentId(modeOrId);
        window.location.hash = `#/security-response/${modeOrId}`;
      } else {
        setSelectedIncidentId(null);
        window.location.hash = '#/security-response';
      }
      setCurrentScreen('security-response');
      return;
    }

    if (screen === 'detection-studio') {
      setStudioMode(modeOrId === 'upload' || modeOrId === 'live' ? modeOrId : undefined);
      window.location.hash = '#/detection-studio';
      setCurrentScreen('detection-studio');
      return;
    }

    if (screen === 'operator-login') {
      handleLogout();
      return;
    }

    window.location.hash = `#/${screen}`;
    setCurrentScreen(screen);
  };

  const handleSignInSuccess = () => {
    if(isAuthenticated())navigateTo('security-setup');
  };

  const handleLogout = () => {
    logout();
    setSelectedIncidentId(null);
    setActiveVideoUrl(null);
    setActiveVideoFile(null);
    setActiveSourceId(null);
    setActiveVideoName(null);
    setLatestFrame(null);
    setExtractedFrames([]);
    setCurrentScreen('operator-login');
    window.location.hash = '#/operator-login';
  };

  const clearActiveCapture = () => {
    setSelectedIncidentId(null);
    setLatestFrame(null);
    setActiveVideoUrl(null);
    setActiveVideoFile(null);
    setActiveSourceId(null);
    setActiveVideoName(null);
    setExtractedFrames([]);
    setStudioMode(undefined);
    try {
      localStorage.removeItem('sightline_latest_frame');
      localStorage.removeItem('sightline_video_name');
    } catch { /* Session state is still cleared if browser storage is unavailable. */ }
    navigateTo('dashboard');
  };

  const handleFrameExtracted = (
    frameUrl: string,
    videoUrl?: string,
    frames?: Frame[],
    videoName?: string
  ) => {
    setLatestFrame(frameUrl || null);
    if (videoUrl !== undefined) {
      setActiveVideoUrl(videoUrl || null);
      if (!videoUrl) {
        setActiveVideoFile(null);
        setActiveSourceId(null);
      }
    }
    if (videoName !== undefined) {
      setActiveVideoName(videoName || null);

    }
    if (frames) {
      setExtractedFrames(frames);
    }
  };

  const handleVideoUploaded = (videoUrl: string, videoName: string, file?: File) => {
    setActiveVideoFile(file || null);
    setActiveSourceId(null);
    setActiveVideoUrl(videoUrl);
    setActiveVideoName(videoName);
    setExtractedFrames([]);
    setLatestFrame(null);

  };

  if (isSessionLoading) {
    return (
      <div className="min-h-screen w-full bg-[#030b14] flex justify-center items-center">
        <div className="flex flex-col items-center gap-3">
          <MaterialIcon name="shield" className="text-[36px] text-[#4edea3] animate-pulse" />
          <span className="font-mono text-xs font-bold text-[#d4e4fa] tracking-widest">
            Loading SightLine…
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen w-full bg-[#030b14] flex justify-center items-start overflow-x-hidden">
      {/* Mobile-width tactical viewport container */}
      <main key={accountKey||'signed-out'} className="w-full max-w-[430px] min-h-screen bg-[#051424] shadow-2xl relative flex flex-col border-x border-[#273647]/30">
        {currentScreen === 'operator-login' && (
          <OperatorLoginScreen onSuccess={()=>void handleSignInSuccess()} />
        )}

        {currentScreen === 'threat-detail' && (
          <ThreatDetailScreen
            onIncidentResolved={resolveIncident}
            onFalseAlarmCleared={clearActiveCapture}
            onBack={() => navigateTo('dashboard')}
            onNavigate={navigateTo}
            latestFrame={latestFrame}
            videoUrl={activeVideoUrl}
            incidentId={selectedIncidentId}
          />
        )}

        {currentScreen === 'dismiss-incident' && <DismissIncidentScreen incidentId={selectedIncidentId} onBack={() => navigateTo('threat-detail',selectedIncidentId || undefined)} onDismissed={clearActiveCapture}/> }

        {currentScreen === 'dashboard' && (
          <DashboardScreen
            onNavigate={navigateTo}
            videoUrl={activeVideoUrl}
            videoName={activeVideoName}
            latestFrame={latestFrame}
            onVideoUploaded={handleVideoUploaded}
          />
        )}

        {setupNotice&&<div role="status" className="fixed top-20 left-1/2 -translate-x-1/2 z-50 w-[calc(100%-2rem)] max-w-[398px] rounded-xl bg-[#12352f] border border-[#4edea3]/50 text-[#4edea3] px-4 py-3 text-sm shadow-xl">{setupNotice}</div>}
        {currentScreen === 'security-setup' && <SecuritySetupScreen onNavigate={navigateTo} onDone={()=>navigateTo(selectedIncidentId?'security-response':'dashboard',selectedIncidentId||undefined)} onSaved={()=>{setSetupNotice('Security details saved to your account.');navigateTo(selectedIncidentId?'security-response':'dashboard',selectedIncidentId||undefined);}}/>}

        {currentScreen === 'security-response' && (
          <SecurityResponseScreen
            onBack={() =>
              selectedIncidentId
                ? navigateTo('threat-detail', selectedIncidentId)
                : navigateTo('threat-detail')
            }
            onNavigate={navigateTo}
            incidentId={selectedIncidentId}
            onFalseAlarmCleared={clearActiveCapture}
          />
        )}

        {currentScreen === 'detection-studio' && (
          <DetectionStudioScreen
            onNavigate={navigateTo}
            onTriggerAlert={(incId) => navigateTo('threat-detail', incId)}
            onFrameExtracted={handleFrameExtracted}
            videoUrl={activeVideoUrl}
            videoName={activeVideoName}
            onVideoUploaded={handleVideoUploaded}
            initialMode={studioMode}
            selectedFile={activeVideoFile}
            uploadedSourceId={activeSourceId}
            onSourceReady={setActiveSourceId}
          />
        )}

        {currentScreen === 'history-logs' && (
          <HistoryLogsScreen onNavigate={navigateTo} />
        )}
      </main>
    </div>
  );
}
