/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useRef, useEffect } from 'react';
import { MaterialIcon } from '../common/MaterialIcon.tsx';
import { getCurrentOperator, logout } from '../../services/auth.ts';

interface TacticalHeaderProps {
  rightBadge?: string;
  onProfileClick?: () => void;
  isBackendConnected?: boolean;
  isCheckingConnection?: boolean;
  onLogout?: () => void;
}

export const TacticalHeader: React.FC<TacticalHeaderProps> = ({
  rightBadge,
  onProfileClick,
  isBackendConnected = false,
  isCheckingConnection = false,
  onLogout,
}) => {
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const profileButtonRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const modalCloseButtonRef = useRef<HTMLButtonElement | null>(null);
  const operator = getCurrentOperator();

  const handleOpenProfile = () => {
    setShowProfileMenu(true);
  };

  const handleCloseProfile = () => {
    setShowProfileMenu(false);
    profileButtonRef.current?.focus();
  };

  // Keyboard Escape listener
  useEffect(() => {
    if (!showProfileMenu) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if(e.key==='Tab'){
        const controls=dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href]');
        if(controls?.length){const first=controls[0],last=controls[controls.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
      }
      if (e.key === 'Escape') {
        handleCloseProfile();
      }
    };

    window.addEventListener('keydown', onKeyDown);
    modalCloseButtonRef.current?.focus();

    return () => window.removeEventListener('keydown', onKeyDown);
  }, [showProfileMenu]);

  const handleLogoutClick = async () => {
    setShowProfileMenu(false);
    if (onLogout) onLogout();
    else {await logout(); if(onProfileClick)onProfileClick();else window.location.hash='#/operator-login';}
  };

  return (
    <>
      <header className="fixed top-0 max-w-[430px] w-full z-40 bg-[#051424]/90 backdrop-blur-xl shadow-[0_1px_12px_rgba(0,0,0,0.35)] border-b border-[#273647]/50">
        <div className="h-16 px-4 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-10 h-10 rounded-lg bg-[#1c2b3c] border border-[#273647] flex items-center justify-center text-[#4edea3] shadow-sm shrink-0">
              <MaterialIcon name="filter_center_focus" className="text-[20px]" />
            </div>
            <div className="flex flex-col min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="font-sans text-[16px] font-semibold tracking-tight text-[#d4e4fa]">
                  SightLine
                </span>
                <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-[#273647] text-[#4edea3] font-bold leading-none">
                  AI
                </span>
              </div>
              <span className="font-mono text-[11px] text-[#e4beba]/80 flex items-center gap-1.5 leading-tight truncate">
                <span
                  className={`w-2 h-2 rounded-full inline-block shrink-0 ${
                    isBackendConnected ? 'bg-[#4edea3] animate-pulse' : 'bg-amber-400'
                  }`}
                />
                <span className="truncate">
                  {isCheckingConnection?'CHECKING CONNECTION':isBackendConnected ? 'MODEL CONNECTED' : 'API CONNECTION UNAVAILABLE'}
                </span>
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {!isBackendConnected && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/15 border border-amber-500/40 text-amber-300 font-mono text-[11px] font-extrabold tracking-wider shadow-sm">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                {isCheckingConnection?'CHECKING':'OFFLINE'}
              </div>
            )}
            {rightBadge && (
              <div className="flex items-center px-2.5 py-1 rounded bg-[#0d1c2d] border border-[#273647]">
                <span className="font-mono text-[11px] text-[#4edea3] font-bold">
                  {rightBadge}
                </span>
              </div>
            )}
            <button
              ref={profileButtonRef}
              type="button"
              onClick={handleOpenProfile}
              className="w-10 h-10 min-w-[40px] min-h-[40px] rounded-full bg-[#ffb3ad] flex items-center justify-center text-[#68000a] shadow-sm hover:brightness-105 active:scale-95 transition-all cursor-pointer"
              aria-label="Open Operator Profile Menu"
              aria-haspopup="dialog"
              aria-expanded={showProfileMenu}
            >
              <MaterialIcon name="person" className="text-[20px]" />
            </button>
          </div>
        </div>
      </header>

      {showProfileMenu && (
        <div className="fixed inset-0 z-50 bg-[#010a14]/75 backdrop-blur-sm flex items-center justify-center p-5" onClick={e=>{if(e.target===e.currentTarget)handleCloseProfile();}}>
          <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="operator-profile-title" className="w-full max-w-[350px] rounded-3xl bg-[#0d1c2d] border border-[#273647] shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 pt-4 pb-3"><h2 id="operator-profile-title" className="text-base font-semibold text-white">Account</h2><button ref={modalCloseButtonRef} type="button" onClick={handleCloseProfile} aria-label="Close account menu" className="w-9 h-9 rounded-full hover:bg-[#1c2b3c] flex items-center justify-center text-[#94a3b8]"><MaterialIcon name="close" className="text-xl"/></button></div>
            <div className="px-5 pb-5 flex items-center gap-3"><div className="w-12 h-12 rounded-full bg-[#4edea3]/10 border border-[#4edea3]/20 text-[#4edea3] font-semibold text-lg flex items-center justify-center shrink-0">{(operator?.operatorId||'S').slice(0,1).toUpperCase()}</div><div className="min-w-0"><p className="text-sm font-semibold text-white break-words">{operator?.operatorId||'SightLine account'}</p><p className="text-xs text-[#94a3b8] mt-1">Your SightLine account</p></div></div>
            <div className="border-t border-[#273647] px-2 py-2"><button type="button" onClick={()=>{setShowProfileMenu(false);window.location.hash='#/security-setup';}} className="w-full min-h-[70px] px-3 py-3 rounded-xl hover:bg-[#1c2b3c] text-left flex items-center gap-3 group"><div className="w-10 h-10 rounded-xl bg-[#1c2b3c] flex items-center justify-center text-[#4edea3] shrink-0"><MaterialIcon name="location_on" className="text-xl"/></div><div className="flex-1"><p className="text-sm font-medium text-white">Security contacts &amp; location</p><p className="text-[11px] text-[#94a3b8] mt-1">Manage your property and contacts</p></div><MaterialIcon name="chevron_right" className="text-xl text-[#72849b]"/></button></div>
            <div className="border-t border-[#273647] px-2 py-2">
              <a href="https://github.com/BuildWithShaurya-code/sightline-ai" target="_blank" rel="noopener noreferrer" className="w-full min-h-12 px-3 rounded-xl hover:bg-[#1c2b3c] text-left flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-[#1c2b3c] flex items-center justify-center text-[#94a3b8]"><MaterialIcon name="code" className="text-xl" /></div>
                <span className="flex-1 text-sm font-medium text-white">Source &amp; setup guide</span>
                <MaterialIcon name="open_in_new" className="text-lg text-[#72849b]" />
              </a>
            </div>
            <div className="border-t border-[#273647] p-2"><button type="button" onClick={()=>void handleLogoutClick()} className="w-full min-h-12 px-4 rounded-xl hover:bg-red-400/5 text-[#ffb3ad] text-sm font-medium flex items-center gap-3"><MaterialIcon name="logout" className="text-xl"/>Sign out</button></div>
          </div>
        </div>
      )}
    </>
  );
};
