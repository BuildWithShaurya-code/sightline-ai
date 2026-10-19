/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { MaterialIcon } from '../common/MaterialIcon.tsx';
import { TacticalHeader } from '../navigation/TacticalHeader.tsx';
import { BottomNavigation } from '../navigation/BottomNavigation.tsx';
import { ScreenId, Incident, IncidentStatus } from '../../types/sightline.ts';
import { listIncidents, getCachedIncidents, reviewIncident, deleteIncident } from '../../services/api.ts';

interface HistoryLogsScreenProps {
  onNavigate?: (screen: ScreenId, modeOrId?: string) => void;
}

type DateFilterOption = 'all' | 'today' | 'past7days' | 'past30days';

interface PendingDeletion {
  incident: Incident;
  timerId: number;
}

export const HistoryLogsScreen: React.FC<HistoryLogsScreenProps> = ({ onNavigate }) => {
  const [logs, setLogs] = useState<Incident[]>(()=>getCachedIncidents({page:1,page_size:10})?.items||[]);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | IncidentStatus>('all');
  const [dateFilter, setDateFilter] = useState<DateFilterOption>('all');
  const [showFilterPopover, setShowFilterPopover] = useState(false);
  const [isLoading, setIsLoading] = useState(()=>!getCachedIncidents({page:1,page_size:10}));
  const [isRefreshing,setIsRefreshing]=useState(false);
  const [hasLoadError, setHasLoadError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Pagination state
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(()=>getCachedIncidents({page:1,page_size:10})?.pagination.total_pages||1);
  const [totalItems, setTotalItems] = useState<number>(()=>getCachedIncidents({page:1,page_size:10})?.pagination.total_items||0);
  const PAGE_SIZE = 10;

  // Selected incident for the Detail Modal
  const [inspectingIncident, setInspectingIncident] = useState<Incident | null>(null);
  const modalCloseButtonRef = useRef<HTMLButtonElement | null>(null);
  const modalTriggerRef = useRef<HTMLElement | null>(null);

  // Undo toast deletion state
  const [pendingDeletion, setPendingDeletion] = useState<PendingDeletion | null>(null);
  const [undoCountdown, setUndoCountdown] = useState<number>(5);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const loadRevisionRef = useRef(0);
  const countdownRef = useRef<number | null>(null);
  const pendingRef = useRef<PendingDeletion | null>(null);
  pendingRef.current = pendingDeletion;

  // Debounce search input (300ms)
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedQuery(searchQuery.trim());
      setCurrentPage(1); // Reset to first page on search
    }, 300);
    return () => clearTimeout(handler);
  }, [searchQuery]);

  // Load incidents from backend
  const loadData = useCallback(async (signal?: AbortSignal) => {
    const revision = ++loadRevisionRef.current;
    setIsRefreshing(true);
    setHasLoadError(false);
    setErrorMessage(null);

    try {
      let createdAfter: string | undefined;
      if (dateFilter !== 'all') {
        const cutoff = new Date();
        if (dateFilter === 'today') cutoff.setHours(0, 0, 0, 0);
        else {cutoff.setHours(0,0,0,0);cutoff.setDate(cutoff.getDate() - (dateFilter === 'past7days' ? 7 : 30));}
        createdAfter = cutoff.toISOString();
      }
      const params={
        q: debouncedQuery || undefined,
        status: statusFilter !== 'all' ? statusFilter : undefined,
        page: currentPage,
        page_size: PAGE_SIZE,
        created_after: createdAfter,
      };
      const cached=getCachedIncidents(params);
      setIsLoading(!cached);
      if(cached){
        setLogs(cached.items.filter(item=>item.id!==pendingRef.current?.incident.id));
        setTotalPages(cached.pagination.total_pages||1);setTotalItems(cached.pagination.total_items);
      }else setLogs([]);
      const response=await listIncidents(params,{signal});
      if (signal?.aborted || revision !== loadRevisionRef.current) return;

      setLogs(response.items.filter(item => item.id !== pendingRef.current?.incident.id));
      setTotalPages(response.pagination.total_pages || 1);
      setTotalItems(response.pagination.total_items || response.items.length);
    } catch (err: unknown) {
      if (signal?.aborted || revision !== loadRevisionRef.current) return;
      console.error('HistoryLogs: Error loading incidents:', err);
      setHasLoadError(true);
      const msg = err instanceof Error ? err.message : 'Failed to retrieve incidents from database';
      setErrorMessage(msg);
      setLogs([]);
    } finally {
      if (!signal?.aborted && revision === loadRevisionRef.current) {setIsLoading(false);setIsRefreshing(false);}
    }
  }, [debouncedQuery, statusFilter, currentPage, dateFilter]);

  useEffect(() => {
    const controller = new AbortController();
    void loadData(controller.signal);
    return () => controller.abort();
  }, [loadData]);

  // Only leaving History commits a pending delete; changing filters must preserve Undo.
  useEffect(() => () => {
    loadRevisionRef.current += 1;
    if (countdownRef.current !== null) window.clearInterval(countdownRef.current);
    const pending = pendingRef.current;
    pendingRef.current = null;
    if (pending) {
      window.clearTimeout(pending.timerId);
      void deleteIncident(pending.incident.id).catch(err => console.warn('Pending history delete failed:', err));
    }
  }, []);

  // Keyboard Escape listener for Detail Modal
  useEffect(() => {
    if (!inspectingIncident) return;

    const onModalKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeDetailModal();
      }
    };

    window.addEventListener('keydown', onModalKeyDown);
    modalCloseButtonRef.current?.focus();

    return () => window.removeEventListener('keydown', onModalKeyDown);
  }, [inspectingIncident]);

  const openDetailModal = (item: Incident, triggerEl?: HTMLElement) => {
    modalTriggerRef.current = triggerEl || (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    setInspectingIncident(item);
  };

  const closeDetailModal = () => {
    setInspectingIncident(null);
    modalTriggerRef.current?.focus();
  };

  const handleUpdateStatus = async (id: string, newStatus: IncidentStatus) => {
    try {
      const updated = await reviewIncident(id, newStatus, `Operator updated status to ${newStatus}`);
      setLogs((prev) =>
        prev.map((item) => (item.id === id ? { ...item, status: updated.status } : item))
      );
      if (inspectingIncident && inspectingIncident.id === id) {
        setInspectingIncident((prev) => (prev ? { ...prev, status: updated.status } : null));
      }
      setToastMessage(`Incident status updated to ${newStatus.toUpperCase()}`);
      setTimeout(() => setToastMessage(null), 2500);
    } catch (err: unknown) {
      console.error('Failed to update status:', err);
      const msg = err instanceof Error ? err.message : 'Update failed';
      setToastMessage(`Error: ${msg}`);
      setTimeout(() => setToastMessage(null), 2500);
    }
  };

  const handleDeleteWithUndo = (incident: Incident) => {
    if (pendingRef.current) {
      clearTimeout(pendingRef.current.timerId);
      void deleteIncident(pendingRef.current.incident.id).catch(() => void loadData());
    }
    if (countdownRef.current !== null) window.clearInterval(countdownRef.current);

    // Optimistically remove from view during the 5s window
    setLogs((prev) => prev.filter((item) => item.id !== incident.id));
    if (inspectingIncident?.id === incident.id) {
      setInspectingIncident(null);
    }

    setUndoCountdown(5);

    const countdownInterval = window.setInterval(() => {
      setUndoCountdown((c) => {
        if (c <= 1) {
          clearInterval(countdownInterval);
          return 0;
        }
        return c - 1;
      });
    }, 1000);

    countdownRef.current = countdownInterval;
    const timerId = window.setTimeout(async () => {
      clearInterval(countdownInterval);
      pendingRef.current = null;
      setPendingDeletion(null);

      // Execute actual backend soft-deletion
      try {
        await deleteIncident(incident.id);
        void loadData();
        setToastMessage(`Incident #${incident.id} deleted from database`);
        setTimeout(() => setToastMessage(null), 2000);
      } catch (err: unknown) {
        console.error('Backend deletion failed:', err);
        // Rollback on failure
        void loadData();
        setToastMessage(`Delete failed: could not remove #${incident.id}`);
        setTimeout(() => setToastMessage(null), 3000);
      }
    }, 5000);

    pendingRef.current = { incident, timerId };
    setPendingDeletion(pendingRef.current);
  };

  const handleUndoDelete = () => {
    if (!pendingDeletion) return;
    clearTimeout(pendingDeletion.timerId);
    if (countdownRef.current !== null) window.clearInterval(countdownRef.current);
    pendingRef.current = null;

    // Restore to list without sending DELETE
    void loadData();
    setPendingDeletion(null);
    setToastMessage(`Incident #${pendingDeletion.incident.id} restored`);
    setTimeout(() => setToastMessage(null), 2200);
  };

  // Date filtering happens on the server before pagination.
  const filteredLogs = logs;

  const activeFiltersCount = (statusFilter !== 'all' ? 1 : 0) + (dateFilter !== 'all' ? 1 : 0);

  const formatDateTime = (isoString?: string): string => {
    if (!isoString) return 'Not available';
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return isoString;
      return `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} • ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    } catch {
      return isoString;
    }
  };

  return (
    <div className="flex flex-col w-full min-h-screen bg-[#051424] text-[#d4e4fa] pb-24 select-none">
      {/* Top Header */}
      <TacticalHeader
        isBackendConnected={true}
        rightBadge="AUDIT TRAIL"
        onProfileClick={() => onNavigate?.('operator-login')}
      />

      {/* Main Content Area */}
      <div className="flex flex-col p-4 pt-20 gap-3.5">
        {/* Title Row */}
        <div className="flex items-center justify-between px-0.5">
          <h1 className="font-sans text-xl font-bold tracking-tight text-white">
            Forensic Threat History
          </h1>
          <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-[#0d1c2d] border border-[#273647]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#4edea3]" />
            <span className="font-mono text-[11px] font-bold text-[#d4e4fa]">
              {totalItems} RECORDS
            </span>
          </div>
        </div>

        {/* Search Bar with Filter Action */}
        <div className="relative w-full">
          <div className="w-full flex items-center bg-[#0d1c2d] border border-[#273647] rounded-xl px-3 py-1 shadow-sm focus-within:border-[#4edea3]/60 transition-all">
            <MaterialIcon name="search" className="text-[20px] text-[#94a3b8] mr-2 shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by incident ID, source, or channel..."
              className="w-full bg-transparent font-mono text-xs text-white placeholder-[#94a3b8] focus:outline-none py-1.5"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="w-8 h-8 flex items-center justify-center text-[#94a3b8] hover:text-white cursor-pointer shrink-0"
                aria-label="Clear search query"
              >
                <MaterialIcon name="close" className="text-[16px]" />
              </button>
            )}
            <button
              type="button"
              onClick={() => setShowFilterPopover(!showFilterPopover)}
              className={`relative flex items-center justify-center w-10 h-10 min-w-[40px] min-h-[40px] rounded-lg border transition-all cursor-pointer shrink-0 ${
                showFilterPopover || activeFiltersCount > 0
                  ? 'bg-[#1c2b3c] border-[#4edea3] text-[#4edea3]'
                  : 'bg-transparent border-transparent text-[#94a3b8] hover:text-white'
              }`}
              aria-label="Filter incidents by status and date"
              aria-expanded={showFilterPopover}
            >
              <MaterialIcon name="tune" className="text-[18px]" />
              {activeFiltersCount > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-[#4edea3] text-[#003824] font-mono text-[11px] font-bold flex items-center justify-center shadow-sm">
                  {activeFiltersCount}
                </span>
              )}
            </button>
          </div>

          {/* Filter Popover */}
          {showFilterPopover && (
            <div
              role="region"
              aria-label="Incident Filters"
              className="absolute top-full left-0 right-0 mt-2 z-40 rounded-2xl bg-[#0d1c2d] border border-[#273647] p-4 shadow-2xl backdrop-blur-xl flex flex-col gap-3"
            >
              <div className="flex items-center justify-between border-b border-[#273647] pb-2">
                <span className="font-mono text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                  <MaterialIcon name="filter_list" className="text-[15px] text-[#4edea3]" />
                  Filter Incidents
                </span>
                <button
                  type="button"
                  onClick={() => setShowFilterPopover(false)}
                  className="w-8 h-8 min-w-[32px] min-h-[32px] flex items-center justify-center text-[#94a3b8] hover:text-white cursor-pointer"
                  aria-label="Close filters"
                >
                  <MaterialIcon name="close" className="text-[16px]" />
                </button>
              </div>

              {/* Status Filter Options */}
              <div className="flex flex-col gap-1.5">
                <span className="font-mono text-[11px] text-[#94a3b8] uppercase font-bold">
                  Status
                </span>
                <div className="grid grid-cols-4 gap-1.5">
                  {(['all', 'unreviewed', 'confirmed', 'dismissed'] as const).map((s) => (
                    <button
                      key={s}
                      type="button"
                      aria-pressed={statusFilter === s}
                      onClick={() => {
                        setStatusFilter(s);
                        setCurrentPage(1);
                      }}
                      className={`min-h-[40px] py-1.5 px-1.5 rounded-lg font-mono text-[11px] font-bold capitalize transition-all cursor-pointer border ${
                        statusFilter === s
                          ? 'bg-[#4edea3] text-[#003824] border-[#4edea3]'
                          : 'bg-[#051424] text-[#d4e4fa] border-[#273647] hover:border-[#4edea3]/40'
                      }`}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              {/* Date Filter Options */}
              <div className="flex flex-col gap-1.5">
                <span className="font-mono text-[11px] text-[#94a3b8] uppercase font-bold">
                  Date Range
                </span>
                <div className="grid grid-cols-4 gap-1.5">
                  {[
                    { id: 'all', label: 'All' },
                    { id: 'today', label: 'Today' },
                    { id: 'past7days', label: '7 Days' },
                    { id: 'past30days', label: '30 Days' },
                  ].map((d) => (
                    <button
                      key={d.id}
                      type="button"
                      aria-pressed={dateFilter === d.id}
                      onClick={() => { setDateFilter(d.id as DateFilterOption); setCurrentPage(1); }}
                      className={`min-h-[40px] py-1.5 px-1.5 rounded-lg font-mono text-[11px] font-bold transition-all cursor-pointer border ${
                        dateFilter === d.id
                          ? 'bg-[#4edea3] text-[#003824] border-[#4edea3]'
                          : 'bg-[#051424] text-[#d4e4fa] border-[#273647] hover:border-[#4edea3]/40'
                      }`}
                    >
                      {d.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Reset Action */}
              <div className="flex items-center justify-between pt-2 border-t border-[#273647]">
                <button
                  type="button"
                  onClick={() => {
                    setStatusFilter('all');
                    setDateFilter('all');
                    setCurrentPage(1);
                  }}
                  className="font-mono text-xs text-[#e4beba]/80 hover:text-white underline cursor-pointer min-h-[40px] flex items-center"
                >
                  Reset all filters
                </button>
                <button
                  type="button"
                  onClick={() => setShowFilterPopover(false)}
                  className="min-h-[40px] py-1 px-4 rounded-full bg-[#1c2b3c] border border-[#273647] text-[#4edea3] font-mono text-xs font-bold hover:bg-[#273647] cursor-pointer"
                >
                  Done
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Filter Quick Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
          {(['all', 'unreviewed', 'confirmed', 'dismissed'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => {
                setStatusFilter(tab);
                setCurrentPage(1);
              }}
              className={`px-3 py-1.5 rounded-full font-mono text-xs font-bold capitalize transition-all shrink-0 cursor-pointer border ${
                statusFilter === tab
                  ? 'bg-[#4edea3] text-[#003824] border-[#4edea3]'
                  : 'bg-[#0d1c2d] text-[#94a3b8] border-[#273647] hover:text-white'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {isRefreshing&&!isLoading&&<p role="status" className="text-xs text-[#94a3b8]">Refreshing your history…</p>}
        {/* Loading State */}
        {isLoading && (
          <div className="p-8 rounded-2xl bg-[#0d1c2d] border border-[#273647] flex flex-col items-center justify-center gap-2">
            <MaterialIcon name="sync" className="text-[24px] text-[#4edea3] animate-spin" />
            <span className="font-mono text-xs text-[#94a3b8]">Querying incident database...</span>
          </div>
        )}

        {/* Error State */}
        {hasLoadError && !isLoading && (
          <div className="p-4 rounded-2xl bg-red-950/50 border border-red-500/60 flex flex-col gap-2">
            <span className="font-mono text-xs font-bold text-red-200">
              {errorMessage || 'Failed to load incident history'}
            </span>
            <button
              type="button"
              onClick={() => void loadData()}
              className="self-start px-3 py-1.5 rounded-lg bg-red-900/60 border border-red-500/80 font-mono text-xs text-white"
            >
              Retry
            </button>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !hasLoadError && filteredLogs.length === 0 && (
          <div className="p-8 rounded-2xl bg-[#0d1c2d] border border-[#273647] flex flex-col items-center justify-center text-center gap-3">
            <MaterialIcon name="inbox" className="text-[32px] text-[#94a3b8]/60" />
            <span className="font-sans text-sm font-bold text-white">No incidents match criteria</span>
            <span className="font-mono text-xs text-[#94a3b8] max-w-[240px]">
              {searchQuery || statusFilter !== 'all'
                ? 'Try clearing active search or filters to see all recorded threats.'
                : 'Save a camera alert or analyze a video in Studio. Records belong to the signed-in operator.'}
            </span>
          </div>
        )}

        {/* Incidents Cards List */}
        {!isLoading && !hasLoadError && filteredLogs.length > 0 && (
          <div className="flex flex-col gap-3 mt-1">
            {filteredLogs.map((item) => (
              <div
                key={item.id}
                role="button"
                tabIndex={0}
                aria-label={`Incident ${item.id}, ${item.title || item.sourceId}, status ${item.status}`}
                onKeyDown={(e) => {
                  if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault();
                    onNavigate?.('threat-detail', item.id);
                  }
                }}
                onClick={() => onNavigate?.('threat-detail', item.id)}
                className="w-full rounded-2xl bg-[#0d1c2d] border border-[#273647] p-3.5 flex flex-col gap-2.5 shadow-lg relative group transition-all hover:border-[#4edea3]/50 cursor-pointer"
              >
                {/* Header row with Title, Channel, and Status Badge */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-8 h-8 rounded-lg bg-[#1c2b3c] border border-[#273647] flex items-center justify-center text-[#4edea3] shrink-0">
                      <MaterialIcon name="folder_special" className="text-[18px]" />
                    </div>
                    <div className="flex flex-col min-w-0">
                      <span className="font-sans text-xs font-bold text-white truncate max-w-[180px]">
                        {item.title || item.sourceId}
                      </span>
                      <span className="font-mono text-[11px] text-[#e4beba]/70 truncate max-w-[180px]">
                        #{item.id} • {formatDateTime(item.createdAt)}
                      </span>
                    </div>
                  </div>

                  {/* Status Badge */}
                  <span
                    className={`font-mono text-[11px] font-extrabold px-2.5 py-0.5 rounded-full border shrink-0 ${
                      item.status === 'confirmed'
                        ? 'bg-emerald-950/60 border-emerald-500/60 text-emerald-300'
                        : item.status === 'dismissed'
                        ? 'bg-gray-800 border-gray-600 text-gray-400'
                        : 'bg-amber-950/60 border-amber-500/60 text-amber-300'
                    }`}
                  >
                    {item.status.toUpperCase()}
                  </span>
                </div>

                {/* Thumbnail Strip */}
                {item.frames && item.frames.length > 0 && (
                  <div className="grid grid-cols-4 gap-1.5 pt-1">
                    {item.frames.slice(0, 4).map((f, idx) => (
                      <div
                        key={f.id || idx}
                        className="relative aspect-video rounded-md overflow-hidden border border-[#273647] bg-[#010f1f]"
                      >
                        <img
                          src={f.imageDataUrl}
                          alt={`Keyframe ${idx + 1}`}
                          className="w-full h-full object-cover"
                        />
                        <span className="absolute bottom-0.5 right-0.5 px-1 rounded bg-black/85 font-mono text-[10px] text-[#4edea3]">
                          T+{Math.round(f.timeSeconds)}s
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Source & Detections Row */}
                <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
                  <span className="px-2 py-0.5 rounded-full font-mono text-[11px] font-bold bg-[#010f1f] border border-[#273647] text-[#94a3b8] truncate max-w-[140px]">
                    {item.channel || item.sourceId}
                  </span>
                  {item.detections && item.detections.length > 0 ? (
                    item.detections.slice(0, 3).map((d, dIdx) => (
                      <span
                        key={dIdx}
                        className="px-2 py-0.5 rounded-full font-mono text-[11px] font-bold bg-[#1c2b3c] border border-[#4edea3]/30 text-[#4edea3]"
                      >
                        {d.classId}: {Math.round(d.confidence * 100)}%
                      </span>
                    ))
                  ) : (
                    <span className="px-2 py-0.5 rounded-full font-mono text-[11px] font-bold bg-[#1c2b3c] border border-[#273647] text-[#94a3b8]">
                      UNANALYSED
                    </span>
                  )}
                  <span className="ml-auto font-mono text-[11px] text-[#94a3b8] shrink-0">
                    {item.frames?.length || 0} FRAMES
                  </span>
                </div>

                <button type="button" onClick={e => {e.stopPropagation(); onNavigate?.('security-response', item.id);}} className="text-left rounded-xl border border-[#4edea3]/30 px-3 py-2 text-xs text-[#4edea3]">
                  Security Response: {item.responseStatus || 'Not contacted'} →
                </button>
                {item.status === 'dismissed' && item.review_reason && <p className="text-xs text-[#94a3b8]">Reason: {item.review_reason}</p>}
                {/* Card Action Footer */}
                <div
                  className="flex items-center justify-between pt-2 border-t border-[#273647]/50 mt-0.5"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {item.status !== 'confirmed' && (
                      <button
                        type="button"
                        onClick={() => handleUpdateStatus(item.id, 'confirmed')}
                        className="min-h-[38px] px-2.5 py-1.5 rounded bg-emerald-950/40 hover:bg-emerald-900/60 border border-emerald-500/40 text-emerald-300 font-mono text-[11px] font-bold active:scale-95 transition-all cursor-pointer"
                        title="Mark as confirmed threat"
                      >
                        Confirm
                      </button>
                    )}
                    {item.status !== 'dismissed' && (
                      <button
                        type="button"
                        onClick={() => onNavigate?.('security-response', item.id)}
                        className="min-h-[38px] px-2.5 py-1.5 rounded bg-[#1c2b3c] hover:bg-[#273647] border border-[#273647] text-[#94a3b8] hover:text-white font-mono text-[11px] font-bold active:scale-95 transition-all cursor-pointer"
                        title="Dismiss incident"
                      >
                        Dismiss
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={(e) => openDetailModal(item, e.currentTarget)}
                      className="min-h-[38px] px-2.5 py-1.5 rounded bg-[#1c2b3c] hover:bg-[#273647] border border-[#273647] text-[#d4e4fa] font-mono text-[11px] font-bold active:scale-95 transition-all cursor-pointer flex items-center gap-1"
                    >
                      <MaterialIcon name="info" className="text-[13px]" />
                      <span>Details</span>
                    </button>
                  </div>

                  {/* Discard / Delete Button with 5s Undo Toast */}
                  <button
                    type="button"
                    onClick={() => handleDeleteWithUndo(item)}
                    className="min-h-[38px] flex items-center gap-1 px-3 py-1.5 rounded-lg bg-[#1c2b3c]/80 hover:bg-[#93000a]/25 active:bg-[#93000a]/40 border border-[#273647] hover:border-[#ff5451]/60 text-[#d4e4fa] hover:text-[#ff5451] active:scale-95 transition-all text-xs font-sans font-semibold cursor-pointer group shadow-sm"
                    aria-label={`Discard log ${item.id}`}
                  >
                    <MaterialIcon
                      name="delete_outline"
                      className="text-[16px] text-[#94a3b8] group-hover:text-[#ff5451]"
                    />
                    <span>Delete</span>
                  </button>
                </div>
              </div>
            ))}

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between p-3 rounded-2xl bg-[#0d1c2d] border border-[#273647] mt-2 font-mono text-xs">
                <button
                  type="button"
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  className="px-3 py-1.5 rounded-lg bg-[#1c2b3c] border border-[#273647] text-white disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Previous
                </button>
                <span className="text-[#94a3b8]">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  type="button"
                  disabled={currentPage >= totalPages}
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  className="px-3 py-1.5 rounded-lg bg-[#1c2b3c] border border-[#273647] text-white disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Inspect Detail Modal */}
      {inspectingIncident && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="inspect-modal-title"
          className="fixed inset-0 z-50 bg-[#010f1f]/85 backdrop-blur-md flex items-center justify-center p-4"
        >
          <div className="w-full max-w-[360px] rounded-3xl bg-[#0d1c2d] border border-[#273647] p-5 flex flex-col gap-3 shadow-2xl relative">
            <div className="flex items-center justify-between border-b border-[#273647] pb-2">
              <span id="inspect-modal-title" className="font-mono text-xs font-bold text-white uppercase">
                Incident #{inspectingIncident.id}
              </span>
              <button
                ref={modalCloseButtonRef}
                type="button"
                onClick={closeDetailModal}
                className="w-8 h-8 flex items-center justify-center text-[#94a3b8] hover:text-white"
                aria-label="Close dialog"
              >
                <MaterialIcon name="close" className="text-[18px]" />
              </button>
            </div>

            <div className="flex flex-col gap-2 font-mono text-xs text-[#d4e4fa]">
              <div>
                <span className="text-[#94a3b8]">Source:</span> {inspectingIncident.sourceId}
              </div>
              <div>
                <span className="text-[#94a3b8]">Status:</span>{' '}
                <span className="font-bold uppercase text-[#4edea3]">{inspectingIncident.status}</span>
              </div>
              <div>
                <span className="text-[#94a3b8]">Created:</span> {formatDateTime(inspectingIncident.createdAt)}
              </div>
              <div>
                <span className="text-[#94a3b8]">Detections:</span> {inspectingIncident.detections?.length || 0}
              </div>
            </div>

            <div className="flex items-center gap-2 pt-2 border-t border-[#273647]">
              <button
                type="button"
                onClick={() => {
                  closeDetailModal();
                  onNavigate?.('threat-detail', inspectingIncident.id);
                }}
                className="flex-1 min-h-[40px] rounded-xl bg-[#4edea3] text-slate-950 font-sans text-xs font-bold flex items-center justify-center gap-1"
              >
                <MaterialIcon name="visibility" className="text-[16px]" />
                <span>Open Threat View</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Undo Toast Notification */}
      {pendingDeletion && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-20 inset-x-4 flex justify-center z-50 pointer-events-none"
        >
          <div className="flex items-center justify-between gap-3 px-4 py-2.5 rounded-2xl bg-[#1c2b3c]/95 border border-amber-500/50 text-white font-mono text-xs shadow-2xl backdrop-blur-md pointer-events-auto max-w-[360px] w-full">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
              <span>Deleting in {undoCountdown}s...</span>
            </div>
            <button
              type="button"
              onClick={handleUndoDelete}
              className="px-3 py-1 rounded-lg bg-[#4edea3] text-slate-950 font-bold active:scale-95 transition-all"
            >
              Undo
            </button>
          </div>
        </div>
      )}

      {/* Standard Toast Notification */}
      {toastMessage && !pendingDeletion && (
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
      <BottomNavigation activeScreen="history-logs" onNavigate={onNavigate} />
    </div>
  );
};
