"""
SightLine AI - Video Analysis Worker
Performs atomic job claiming, frame sampling, neural inference via InferenceService,
bounded evidence keyframe selection (4-8 frames), cancellation checking, and transactional persistence.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
import threading
from typing import Any, Dict, List, Optional, Tuple
import uuid

import cv2
import numpy as np

from ..config import get_settings
from ..db.database import DatabaseManager
from .inference_service import InferenceService
from .storage import LocalMediaStorage

logger = logging.getLogger("sightline.worker")


class VideoWorker:
    def __init__(
        self,
        worker_id: Optional[str] = None,
        db: Optional[DatabaseManager] = None,
        storage: Optional[LocalMediaStorage] = None,
        inference_service: Optional[InferenceService] = None,
        stop_event: Optional[threading.Event] = None,
    ):
        self.settings = get_settings()
        self.stop_event = stop_event or threading.Event()
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.db = db or DatabaseManager.get_instance()
        self.storage = storage or LocalMediaStorage(self.settings.media_dir)
        self.inference_service = inference_service or InferenceService.get_instance()

    def process_job_sync(self, job_id: str) -> Dict[str, Any]:
        """
        Executes complete video inference workflow synchronously for a claimed job.
        Safe to run in background threadpool or standalone worker process.
        """
        job = self.db.get_job(job_id)
        if not job:
            raise ValueError(f"Job '{job_id}' not found.")

        if job["status"] != "processing" or job.get("worker_id") != self.worker_id:
            raise ValueError("Analysis must be atomically claimed by this worker before processing.")

        user_id = job["user_id"]
        source_id = job["source_id"]
        targets = job.get("targets", ["person", "mask", "knife"])
        conf_threshold = job.get("confidence_threshold", 0.25)
        sample_rate_sec = job.get("sample_rate_sec", 0.5)

        source = self.db.get_source(source_id)
        if not source:
            self.db.mark_job_failed(job_id, f"Source '{source_id}' does not exist.")
            return {"status": "failed", "error": f"Source '{source_id}' missing"}

        # Locate media file
        clean_ext = Path(source["original_filename"]).suffix.lower() or ".mp4"
        rel_media_path = f"videos/{source_id}{clean_ext}"
        video_path = self.storage.get_media_path(rel_media_path)

        if self.settings.storage_backend == 'supabase':
            from .cloud_storage import CloudStorage
            CloudStorage(self.settings).download('source-videos', source['storage_key'], video_path, self.settings.max_upload_size_bytes)

        if not video_path.exists() or not video_path.is_file():
            self.db.mark_job_failed(job_id, f"Media file for source '{source_id}' not found on disk.")
            return {"status": "failed", "error": "Media file missing"}

        # Open video capture
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            self.db.mark_job_failed(job_id, "Failed to open video container for decoding.")
            return {"status": "failed", "error": "Decoder failed"}

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if fps <= 0 or total_frames <= 0:
            cap.release()
            self.db.mark_job_failed(job_id, "Video contains zero playable frames or invalid FPS metadata.")
            return {"status": "failed", "error": "Invalid video stream"}

        # Calculate sampling step
        step_frames = max(1, int(round(fps * sample_rate_sec)))

        logger.info(
            "Worker [%s] processing job [%s]: %dx%d, %.1f fps, %d frames (step: %d)",
            self.worker_id,
            job_id,
            width,
            height,
            fps,
            total_frames,
            step_frames,
        )

        started = time.monotonic()
        candidate_frames: List[Dict[str, Any]] = []
        all_detections: List[Dict[str, Any]] = []
        last_progress_reported = 0

        try:
            curr_frame_idx = 0
            while curr_frame_idx < total_frames:
                self._check_deadline(started)
                # Check cancellation request before processing next frame
                if self.db.is_cancellation_requested(job_id):
                    logger.info("Cancellation requested for job [%s]. Stopping processing.", job_id)
                    cap.release()
                    self.db.mark_job_cancelled(job_id)
                    return {"status": "cancelled", "job_id": job_id}

                cap.set(cv2.CAP_PROP_POS_FRAMES, curr_frame_idx)
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                video_offset_sec = round(curr_frame_idx / fps, 3)

                # Run inference on frame
                inference_res = self.inference_service.infer_frame_sync(
                    frame=frame,
                    orig_width=width,
                    orig_height=height,
                    targets=targets,
                    confidence_threshold=conf_threshold,
                    request_id=f"job-{job_id}-f{curr_frame_idx}",
                )

                self._check_deadline(started)
                if inference_res.detections_count > 0:
                    candidate_frames.append({
                        "frame_index": curr_frame_idx,
                        "time_seconds": video_offset_sec,
                        "frame_bgr": frame.copy(),
                        "detections": inference_res.detections,
                        "max_confidence": max(d.confidence for d in inference_res.detections),
                    })

                if len(candidate_frames) > 24:
                    candidate_frames = self._select_evidence_keyframes(candidate_frames, min_k=8, max_k=16)

                # Update progress periodically
                progress = int((curr_frame_idx / total_frames) * 100)
                if progress >= last_progress_reported + 10:
                    self.db.update_job_progress(job_id, progress)
                    last_progress_reported = progress

                curr_frame_idx += step_frames

            cap.release()

            self._check_deadline(started)
            # Check cancellation again before finalization
            if self.db.is_cancellation_requested(job_id):
                self.db.mark_job_cancelled(job_id)
                return {"status": "cancelled", "job_id": job_id}

            # ------------------------------------------------------------------
            # Evidence Selection (Bounded: 4 to 8 Keyframes)
            # ------------------------------------------------------------------
            if not candidate_frames:
                # No requested targets detected: Complete job honestly with 0 incidents!
                logger.info("Job [%s] completed with zero detections. No incident generated.", job_id)
                self.db.mark_job_completed(job_id, incident_id=None)
                return {"status": "completed", "incident_id": None, "detections_count": 0}

            selected_candidates = self._select_evidence_keyframes(candidate_frames, min_k=4, max_k=8)

            # Persist keyframes to disk
            evidence_records: List[Dict[str, Any]] = []
            detection_records: List[Dict[str, Any]] = []
            detected_classes_set = set()

            for cand in selected_candidates:
                ev_id = f"ev_{uuid.uuid4().hex[:12]}"
                storage_rel = f"keyframes/{ev_id}.jpg"
                storage_full_path = self.storage.get_media_path(storage_rel)
                storage_full_path.parent.mkdir(parents=True, exist_ok=True)

                # Encode frame to JPEG
                _, encoded_jpg = cv2.imencode(".jpg", cand["frame_bgr"], [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                storage_full_path.write_bytes(encoded_jpg.tobytes())

                # Generate data URL or direct image URL
                import base64
                b64_str = base64.b64encode(encoded_jpg.tobytes()).decode("ascii")
                image_data_url = f"data:image/jpeg;base64,{b64_str}"

                evidence_records.append({
                    "id": ev_id,
                    "source_id": source_id,
                    "user_id": user_id,
                    "evidence_type": "key_frame",
                    "storage_bucket": "evidence-frames",
                    "storage_key": f"{user_id}/{source_id}/{ev_id}.jpg",
                    "video_offset_seconds": cand["time_seconds"],
                    "media_dimensions": {"width": width, "height": height},
                    "image_data_url": image_data_url,
                })

                for det in cand["detections"]:
                    detected_classes_set.add(det.classId)
                    detection_records.append({
                        "id": f"det_{uuid.uuid4().hex[:12]}",
                        "source_id": source_id,
                        "evidence_id": ev_id,
                        "class_id": det.classId,
                        "class_name": det.className,
                        "confidence": det.confidence,
                        "box": list(det.box),
                        "frame_index": cand["frame_index"],
                        "video_offset_seconds": cand["time_seconds"],
                    })

            # Determine severity
            severity = "medium"
            if "knife" in detected_classes_set:
                severity = "critical"
            elif "mask" in detected_classes_set:
                severity = "high"

            incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
            classes_str = ", ".join(sorted(list(detected_classes_set)))
            incident_record = {
                "id": incident_id,
                "source_id": source_id,
                "user_id": user_id,
                "title": f"Threat Alert: {classes_str.title()}",
                "channel": "CAM-01 // SURVEILLANCE NODE",
                "zone": "Zone A // Primary Floor",
                "severity": severity,
                "reason": f"Neural threat detection event identified {classes_str}.",
                "review_status": "unreviewed",
            }

            self._check_deadline(started)
            # Transactional finalization
            final_incident_id = self.db.finalize_analysis_results(
                job_id=job_id,
                incident_dict=incident_record,
                evidence_list=evidence_records,
                detections_list=detection_records,
            )

            if self.db.get_job(job_id)["status"] == "cancelled":
                return {"status": "cancelled", "job_id": job_id}

            logger.info(
                "Job [%s] finalized successfully! Created Incident [%s] with %d evidence frames and %d detections.",
                job_id,
                final_incident_id,
                len(evidence_records),
                len(detection_records),
            )

            return {
                "status": "completed",
                "job_id": job_id,
                "incident_id": final_incident_id,
                "evidence_count": len(evidence_records),
                "detections_count": len(detection_records),
            }

        except Exception as e:
            logger.exception("Error processing video job [%s]: %s", job_id, e)
            self.db.mark_job_failed(job_id, f"Inference worker failed: {str(e)}")
            return {"status": "failed", "error": str(e)}
        finally:
            if "cap" in locals() and cap.isOpened():
                cap.release()

    def _check_deadline(self, started):
        if self.stop_event.is_set():
            raise RuntimeError("Analysis interrupted by server shutdown. Start a new analysis to retry.")
        if time.monotonic() - started >= self.settings.job_timeout_seconds:
            raise TimeoutError("Analysis exceeded its processing time limit.")

    def _select_evidence_keyframes(
        self,
        candidates: List[Dict[str, Any]],
        min_k: int = 4,
        max_k: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Selects between min_k and max_k keyframes emphasizing temporal diversity,
        high confidence, and representation of distinct detected classes.
        """
        if len(candidates) <= max_k:
            return candidates

        # Target desired count
        target_k = min(max_k, max(min_k, len(candidates)))

        # Keep a strongest example of every detected class before filling time coverage.
        # Uniform sampling alone could discard the only frame containing a mask/knife.
        classes = {det.classId for candidate in candidates for det in candidate["detections"]}
        selected_indices = set()
        for class_id in sorted(classes):
            best_index = max(
                range(len(candidates)),
                key=lambda index: max(
                    (det.confidence for det in candidates[index]["detections"] if det.classId == class_id),
                    default=-1,
                ),
            )
            if len(selected_indices) < target_k:
                selected_indices.add(best_index)

        for index in np.linspace(0, len(candidates) - 1, target_k, dtype=int):
            if len(selected_indices) >= target_k:
                break
            selected_indices.add(int(index))
        if len(selected_indices) < target_k:
            for index in range(len(candidates)):
                if len(selected_indices) >= target_k:
                    break
                selected_indices.add(index)
        return [candidates[index] for index in sorted(selected_indices)]

    def process_next_queued_job_sync(self) -> Optional[Dict[str, Any]]:
        """Claims and processes the next available queued job atomically."""
        claimed = self.db.claim_next_queued_job(self.worker_id)
        if not claimed:
            return None
        try:
            return self.process_job_sync(claimed["id"])
        except Exception:
            logger.exception("Claimed job failed before video processing began.")
            self.db.mark_job_failed(claimed["id"], "Video processing could not start. Retry the analysis.")
            return {"status": "failed", "job_id": claimed["id"]}
