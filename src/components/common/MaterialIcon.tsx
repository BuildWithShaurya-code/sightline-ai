/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import {
  Crosshair,
  Hand,
  ChevronRight,
  ChevronsRight,
  CircleCheck,
  User,
  BadgeCheck,
  LogOut,
  Radio,
  FilePlus,
  ArrowRight,
  ArrowLeft,
  Video,
  Camera,
  VideoOff,
  Eye,
  EyeOff,
  Clock,
  Shield,
  Activity,
  VenetianMask,
  PocketKnife,
  AlertCircle,
  AlertTriangle,
  Lock,
  ShieldCheck,
  Fingerprint,
  Key,
  ImageOff,
  MapPin,
  Check,
  RefreshCw,
  Info,
  Search,
  SearchX,
  Receipt,
  Minus,
  Plus,
  Maximize2,
  Volume2,
  Megaphone,
  Trash2,
  SlidersHorizontal,
  Filter,
  X,
  Play,
  Pause,
  Sparkles,
  RotateCcw,
  AlertOctagon,
  LayoutGrid,
  Focus,
  History,
  FolderCheck,
  LucideIcon,
} from 'lucide-react';

interface MaterialIconProps {
  name: string;
  className?: string;
  filled?: boolean;
}

const ICON_MAP: Record<string, LucideIcon> = {
  filter_center_focus: Crosshair,
  touch_app: Hand,
  chevron_right: ChevronRight,
  keyboard_double_arrow_right: ChevronsRight,
  check_circle: CircleCheck,
  person: User,
  badge: BadgeCheck,
  logout: LogOut,
  radar: Radio,
  note_add: FilePlus,
  arrow_forward: ArrowRight,
  arrow_back: ArrowLeft,
  videocam: Video,
  photo_camera: Camera,
  videocam_off: VideoOff,
  visibility: Eye,
  visibility_off: EyeOff,
  pending_actions: Clock,
  shield: Shield,
  wifi_tethering: Radio,
  sensors: Activity,
  masks: VenetianMask,
  hardware: PocketKnife,
  error: AlertCircle,
  error_outline: AlertTriangle,
  lock: Lock,
  verified_user: ShieldCheck,
  fingerprint: Fingerprint,
  vpn_key: Key,
  schedule: Clock,
  image_not_supported: ImageOff,
  location_on: MapPin,
  check: Check,
  sync: RefreshCw,
  info: Info,
  search: Search,
  search_off: SearchX,
  saved_search: Search,
  receipt_long: Receipt,
  receipt: Receipt,
  remove: Minus,
  add: Plus,
  center_focus_weak: Maximize2,
  volume_up: Volume2,
  campaign: Megaphone,
  delete_outline: Trash2,
  delete: Trash2,
  tune: SlidersHorizontal,
  filter_list: Filter,
  close: X,
  play_arrow: Play,
  pause: Pause,
  auto_awesome: Sparkles,
  refresh: RotateCcw,
  sync_problem: AlertOctagon,
  grid_view: LayoutGrid,
  center_focus_strong: Focus,
  warning: AlertTriangle,
  manage_history: History,
  folder_special: FolderCheck,
};

export const MaterialIcon: React.FC<MaterialIconProps> = ({
  name,
  className = 'text-[20px]',
}) => {
  const IconComponent = ICON_MAP[name] || AlertCircle;

  // Extract pixel size if defined in text-[XXpx]
  let size = 20;
  const match = className.match(/text-\[(\d+)px\]/);
  if (match && match[1]) {
    size = parseInt(match[1], 10);
  }

  return (
    <span
      className={`inline-flex items-center justify-center shrink-0 ${className}`}
      style={{ width: `${size}px`, height: `${size}px` }}
      aria-hidden="true"
    >
      <IconComponent size={size} strokeWidth={2.2} />
    </span>
  );
};
