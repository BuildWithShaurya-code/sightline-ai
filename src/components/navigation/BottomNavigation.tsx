/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { MaterialIcon } from '../common/MaterialIcon.tsx';
import { ScreenId } from '../../types/sightline.ts';

interface BottomNavigationProps {
  activeScreen: ScreenId;
  onNavigate?: (screen: ScreenId) => void;
}

export const BottomNavigation: React.FC<BottomNavigationProps> = ({
  activeScreen,
  onNavigate,
}) => {
  const tabs: Array<{ id: ScreenId; label: string; icon: string }> = [
    { id: 'dashboard', label: 'Dashboard', icon: 'grid_view' },
    { id: 'detection-studio', label: 'Studio', icon: 'center_focus_strong' },
    { id: 'threat-detail', label: 'Alerts', icon: 'warning' },
    { id: 'history-logs', label: 'History', icon: 'manage_history' },
  ];

  return (
    <nav
      aria-label="Tactical Navigation"
      className="fixed bottom-0 max-w-[430px] w-full z-40 bg-[#051424]/95 backdrop-blur-xl border-t border-[#273647]/60 shadow-[0_-1px_16px_rgba(0,0,0,0.4)]"
    >
      <div className="flex justify-around items-center h-16 px-4">
        {tabs.map((tab) => {
          const isActive =
            activeScreen === tab.id ||
            (tab.id === 'threat-detail' && (activeScreen === 'security-response' || activeScreen === 'dispatch-receipt'));

          return (
            <button
              key={tab.id}
              type="button"
              aria-current={isActive ? 'page' : undefined}
              onClick={() => onNavigate?.(tab.id)}
              className={`flex flex-col items-center justify-center gap-1 transition-all min-h-[44px] cursor-pointer ${
                isActive
                  ? 'min-w-[72px] py-1.5 px-3.5 rounded-full text-[#4edea3] bg-[#1c2b3c] border border-[#273647] shadow-[0_2px_8px_rgba(0,0,0,0.3)]'
                  : 'min-w-[64px] py-1.5 px-3 rounded-full text-[#e4beba]/80 hover:text-[#d4e4fa]'
              }`}
            >
              <MaterialIcon name={tab.icon} className="text-[20px]" />
              <span className={`font-mono text-[11px] uppercase tracking-wider ${isActive ? 'font-bold' : 'font-medium'}`}>
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
