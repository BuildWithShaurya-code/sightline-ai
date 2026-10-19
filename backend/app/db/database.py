"""
SightLine AI - Database Layer
Provides transactional, thread-safe persistence for sources, analysis jobs, incidents,
evidence, and detections. Conforms strictly to Supabase SCHEMA_PLAN.md entities.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

from ..config import get_settings
from ..core.errors import LockedError, ValidationError, SightLineError

logger = logging.getLogger("sightline.db")


class DatabaseManager:
    """
    Thread-safe database manager implementing the SightLine AI data schema.
    Uses WAL journal mode, strict foreign key enforcement, and parameterized queries.
    """
    _instance: Optional["DatabaseManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self, db_path: Optional[Path] = None):
        settings = get_settings()
        if db_path:
            self.db_path = Path(db_path).resolve()
        else:
            data_dir = settings.media_dir.parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = data_dir / "sightline.db"

        self._local = threading.local()
        self._init_schema()

    @classmethod
    def get_instance(cls, db_path: Optional[Path] = None) -> "DatabaseManager":
        with cls._instance_lock:
            if cls._instance is None:
                if get_settings().storage_backend == 'supabase' and db_path is None:
                    from .postgres import CloudDatabase
                    cls._instance = CloudDatabase(get_settings())
                else:
                    cls._instance = cls(db_path=db_path)
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance.close_all()
                cls._instance = None

    def get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False,
                isolation_level=None,  # Autocommit mode; explicit transactions with BEGIN/COMMIT
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            self._local.conn = conn
        return self._local.conn

    def close_all(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None

    def _init_schema(self) -> None:
        conn = self.get_connection()
        conn.execute("BEGIN IMMEDIATE;")
        try:
            # 1. Sources table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                storage_bucket TEXT NOT NULL DEFAULT 'source-videos',
                storage_key TEXT NOT NULL UNIQUE,
                media_dimensions TEXT,
                duration_seconds REAL,
                file_size_bytes INTEGER,
                status TEXT NOT NULL DEFAULT 'ready',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            # 2. Analysis Jobs table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS analysis_jobs (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                targets TEXT NOT NULL,
                confidence_threshold REAL NOT NULL DEFAULT 0.25,
                sample_rate_sec REAL NOT NULL DEFAULT 0.5,
                model_version TEXT NOT NULL DEFAULT 'yolo11n-theft-v1',
                settings TEXT NOT NULL DEFAULT '{}',
                idempotency_key TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                progress INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                error_details TEXT,
                cancellation_requested INTEGER NOT NULL DEFAULT 0,
                incident_id TEXT,
                worker_id TEXT,
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CONSTRAINT uq_user_idempotency UNIQUE(user_id, idempotency_key)
            );
            """)

            # 3. Incidents table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                job_id TEXT REFERENCES analysis_jobs(id) ON DELETE SET NULL,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'Surveillance Node 1',
                zone TEXT NOT NULL DEFAULT 'Retail Floor Zone A',
                severity TEXT NOT NULL DEFAULT 'medium',
                reason TEXT NOT NULL,
                review_status TEXT NOT NULL DEFAULT 'unreviewed',
                reviewer_id TEXT,
                reviewer_notes TEXT,
                reviewed_at TEXT,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            # 4. Evidence table (Keyframes and clips)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS evidence (
                id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                evidence_type TEXT NOT NULL DEFAULT 'key_frame',
                storage_bucket TEXT NOT NULL DEFAULT 'evidence-frames',
                storage_key TEXT NOT NULL,
                video_offset_seconds REAL,
                media_dimensions TEXT,
                image_data_url TEXT,
                created_at TEXT NOT NULL
            );
            """)

            # 5. Detections table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
                source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                evidence_id TEXT REFERENCES evidence(id) ON DELETE SET NULL,
                class_id TEXT NOT NULL,
                class_name TEXT NOT NULL,
                confidence REAL NOT NULL,
                box TEXT NOT NULL,
                frame_index INTEGER NOT NULL,
                video_offset_seconds REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            """)

            # 6. Incident-Detection Junction Table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS incident_detection_links (
                incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                detection_id TEXT NOT NULL REFERENCES detections(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                PRIMARY KEY (incident_id, detection_id)
            );
            """)

            # 7. Audit Events table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                actor_id TEXT,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT,
                request_id TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """)

            # 8. Dispatches table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS dispatches (
                id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'telegram',
                destination_reference TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'simulated_provider',
                provider_reference TEXT,
                idempotency_key TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                is_simulated INTEGER NOT NULL DEFAULT 0,
                failure_reason TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                delivered_at TEXT,
                cancelled_at TEXT,
                cancelled_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CONSTRAINT uq_dispatch_idempotency UNIQUE(user_id, idempotency_key)
            );
            """)

            # 9. Operator Security table (PIN hash & Lockout tracking)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS operator_security (
                user_id TEXT PRIMARY KEY,
                pin_hash TEXT NOT NULL,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                last_failed_at TEXT,
                updated_at TEXT NOT NULL
            );
            """)

            # Additive migration: clear evidence from operator views without erasing stored files.
            incident_columns = {row[1] for row in conn.execute("PRAGMA table_info(incidents)")}
            if "evidence_cleared" not in incident_columns:
                conn.execute("ALTER TABLE incidents ADD COLUMN evidence_cleared INTEGER NOT NULL DEFAULT 0")

            # Indexes for high performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sources_user ON sources(user_id, created_at DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user_status ON analysis_jobs(user_id, status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_queued ON analysis_jobs(status, created_at ASC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_user ON incidents(user_id, is_deleted, created_at DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_incident ON evidence(incident_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_detections_job ON detections(job_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dispatches_user ON dispatches(user_id, created_at DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dispatches_incident ON dispatches(incident_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dispatches_status ON dispatches(status);")

            conn.execute("""CREATE TABLE IF NOT EXISTS response_contacts (
                user_id TEXT PRIMARY KEY, securityName TEXT NOT NULL DEFAULT '',
                securityPhone TEXT NOT NULL DEFAULT '', policePhone TEXT NOT NULL DEFAULT '112',
                siteAddress TEXT NOT NULL DEFAULT ''
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS response_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
                incident_id TEXT NOT NULL REFERENCES incidents(id), user_id TEXT NOT NULL,
                kind TEXT NOT NULL, recipient TEXT NOT NULL, detail TEXT NOT NULL,
                created_at TEXT NOT NULL, UNIQUE(user_id, incident_id, event_id)
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_response_incident ON response_events(incident_id, user_id, seq)")
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    # --------------------------------------------------------------------------
    # Sources Operations
    # --------------------------------------------------------------------------
    def create_source(self, source_dict: Dict[str, Any]) -> Dict[str, Any]:
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
        INSERT INTO sources (
            id, user_id, source_type, original_filename, storage_bucket,
            storage_key, media_dimensions, duration_seconds, file_size_bytes,
            status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source_dict["id"],
            source_dict["user_id"],
            source_dict.get("source_type", "video_upload"),
            source_dict["original_filename"],
            source_dict.get("storage_bucket", "source-videos"),
            source_dict["storage_key"],
            json.dumps(source_dict.get("media_dimensions")) if source_dict.get("media_dimensions") else None,
            source_dict.get("duration_seconds"),
            source_dict.get("file_size_bytes"),
            source_dict.get("status", "ready"),
            source_dict.get("created_at", now),
            source_dict.get("updated_at", now),
        ))
        return self.get_source(source_dict["id"], source_dict["user_id"])  # type: ignore

    def get_source(self, source_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        if user_id:
            cursor = conn.execute("SELECT * FROM sources WHERE id = ? AND user_id = ?", (source_id, user_id))
        else:
            cursor = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        if res.get("media_dimensions"):
            res["media_dimensions"] = json.loads(res["media_dimensions"])
        return res

    # --------------------------------------------------------------------------
    # Analysis Jobs Operations
    # --------------------------------------------------------------------------
    def create_analysis_job(
        self,
        user_id: str,
        source_id: str,
        targets: List[str],
        confidence_threshold: float = 0.25,
        sample_rate_sec: float = 0.5,
        idempotency_key: Optional[str] = None,
        job_id: Optional[str] = None,
        max_pending: Optional[int] = None,
        max_pending_per_user: Optional[int] = None,
    ) -> Dict[str, Any]:
        import uuid
        jid = job_id or f"job_{uuid.uuid4().hex[:12]}"
        conn = self.get_connection()
        conn.execute("BEGIN IMMEDIATE;")
        try:
            existing = self.get_job_by_idempotency(user_id, idempotency_key) if idempotency_key else None
            if existing:
                conn.execute("COMMIT;")
                return existing
            total, own = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(user_id = ?), 0) FROM analysis_jobs WHERE status IN ('queued','processing')",
                (user_id,),
            ).fetchone()
            if (max_pending is not None and total >= max_pending) or (max_pending_per_user is not None and own >= max_pending_per_user):
                raise SightLineError("QUEUE_FULL", "Analysis queue is full. Wait for an existing job to finish.", 429)
            result = self.create_job({
                "id": jid, "source_id": source_id, "user_id": user_id,
                "targets": targets, "confidence_threshold": confidence_threshold,
                "sample_rate_sec": sample_rate_sec, "idempotency_key": idempotency_key,
            })
            conn.execute("COMMIT;")
            return result
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def create_job(self, job_dict: Dict[str, Any]) -> Dict[str, Any]:

        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()

        # Check idempotency first if key provided
        idempotency_key = job_dict.get("idempotency_key")
        user_id = job_dict["user_id"]
        if idempotency_key:
            existing = self.get_job_by_idempotency(user_id, idempotency_key)
            if existing:
                return existing

        conn.execute("""
        INSERT INTO analysis_jobs (
            id, source_id, user_id, targets, confidence_threshold,
            sample_rate_sec, model_version, settings, idempotency_key,
            status, progress, cancellation_requested, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_dict["id"],
            job_dict["source_id"],
            user_id,
            json.dumps(job_dict.get("targets", ["person", "mask", "knife"])),
            job_dict.get("confidence_threshold", 0.25),
            job_dict.get("sample_rate_sec", 0.5),
            job_dict.get("model_version", "yolo11n-theft-v1"),
            json.dumps(job_dict.get("settings", {})),
            idempotency_key,
            job_dict.get("status", "queued"),
            job_dict.get("progress", 0),
            1 if job_dict.get("cancellation_requested") else 0,
            job_dict.get("created_at", now),
            job_dict.get("updated_at", now),
        ))
        return self.get_job(job_dict["id"], user_id)  # type: ignore

    def get_job_by_idempotency(self, user_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.execute(
            "SELECT * FROM analysis_jobs WHERE user_id = ? AND idempotency_key = ?",
            (user_id, idempotency_key),
        )
        row = cursor.fetchone()
        return self._format_job_row(row) if row else None

    def get_job(self, job_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        if user_id:
            cursor = conn.execute("SELECT * FROM analysis_jobs WHERE id = ? AND user_id = ?", (job_id, user_id))
        else:
            cursor = conn.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        return self._format_job_row(row) if row else None

    def _format_job_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        d["targets"] = json.loads(d["targets"]) if d.get("targets") else []
        d["settings"] = json.loads(d["settings"]) if d.get("settings") else {}
        d["error_details"] = json.loads(d["error_details"]) if d.get("error_details") else None
        d["cancellation_requested"] = bool(d.get("cancellation_requested"))
        return d

    def claim_next_queued_job(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """
        Atomically claims the oldest queued job.
        Uses BEGIN IMMEDIATE to prevent concurrent race conditions between multiple workers.
        """
        conn = self.get_connection()
        conn.execute("BEGIN IMMEDIATE;")
        try:
            cursor = conn.execute(
                "SELECT id FROM analysis_jobs WHERE status = 'queued' AND cancellation_requested = 0 ORDER BY created_at ASC LIMIT 1"
            )
            row = cursor.fetchone()
            if not row:
                conn.execute("COMMIT;")
                return None

            job_id = row["id"]
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE analysis_jobs SET status = 'processing', worker_id = ?, started_at = ?, updated_at = ? WHERE id = ? AND status = 'queued'",
                (worker_id, now, now, job_id),
            )
            conn.execute("COMMIT;")
            return self.get_job(job_id)
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def update_job_progress(self, job_id: str, progress: int) -> None:
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        clamped_progress = max(0, min(100, progress))
        conn.execute(
            "UPDATE analysis_jobs SET progress = ?, updated_at = ? WHERE id = ? AND status = 'processing'",
            (clamped_progress, now, job_id),
        )

    def request_job_cancellation(self, job_id: str, user_id: str) -> Tuple[bool, str]:
        """
        Requests cancellation. If queued, immediately cancels.
        If processing, flags cancellation_requested for the worker.
        """
        conn = self.get_connection()
        conn.execute("BEGIN IMMEDIATE;")
        try:
            cursor = conn.execute(
                "SELECT status, cancellation_requested FROM analysis_jobs WHERE id = ? AND user_id = ?",
                (job_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                conn.execute("COMMIT;")
                return False, "not_found"

            curr_status = row["status"]
            now = datetime.now(timezone.utc).isoformat()

            if curr_status == "queued":
                conn.execute(
                    "UPDATE analysis_jobs SET status = 'cancelled', completed_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, job_id),
                )
                conn.execute("COMMIT;")
                return True, "cancelled"
            elif curr_status == "processing":
                conn.execute(
                    "UPDATE analysis_jobs SET cancellation_requested = 1, updated_at = ? WHERE id = ?",
                    (now, job_id),
                )
                conn.execute("COMMIT;")
                return True, "cancellation_requested"
            else:
                conn.execute("COMMIT;")
                return False, f"already_{curr_status}"
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def is_cancellation_requested(self, job_id: str) -> bool:
        conn = self.get_connection()
        cursor = conn.execute("SELECT cancellation_requested, status FROM analysis_jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if not row:
            return True
        return bool(row["cancellation_requested"]) or row["status"] == "cancelled"

    def mark_job_cancelled(self, job_id: str) -> None:
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE analysis_jobs SET status = 'cancelled', completed_at = ?, updated_at = ? WHERE id = ? AND status IN ('queued','processing')",
            (now, now, job_id),
        )

    def mark_job_failed(self, job_id: str, error_message: str, error_details: Optional[Dict[str, Any]] = None) -> None:
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
        UPDATE analysis_jobs
        SET status = 'failed', error_message = ?, error_details = ?, completed_at = ?, updated_at = ?
        WHERE id = ? AND status IN ('queued','processing')
        """, (
            error_message,
            json.dumps(error_details) if error_details else None,
            now,
            now,
            job_id,
        ))

    def mark_job_completed(self, job_id: str, incident_id: Optional[str] = None) -> None:
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
        UPDATE analysis_jobs
        SET status = 'completed', progress = 100, incident_id = ?, completed_at = ?, updated_at = ?
        WHERE id = ? AND status IN ('queued','processing') AND cancellation_requested = 0
        """, (incident_id, now, now, job_id))
        conn.execute("UPDATE analysis_jobs SET status='cancelled', completed_at=?, updated_at=? WHERE id=? AND status='processing' AND cancellation_requested=1", (now, now, job_id))

    def recover_interrupted_jobs(self) -> int:
        """Only call after obtaining exclusive local-worker ownership on startup."""
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        result = conn.execute(
            "UPDATE analysis_jobs SET status='failed', error_message='Analysis interrupted by server restart. Start a new analysis to retry.', completed_at=?, updated_at=? WHERE status='processing'",
            (now, now),
        )
        return result.rowcount

    def recover_abandoned_jobs(self, timeout_seconds: int = 600) -> int:
        """Recovers or fails jobs that were left processing if a worker died."""
        conn = self.get_connection()
        conn.execute("BEGIN IMMEDIATE;")
        try:
            now = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute("SELECT id, started_at FROM analysis_jobs WHERE status = 'processing'")
            stale_ids = []
            for r in cursor.fetchall():
                started_at_str = r["started_at"]
                if started_at_str:
                    try:
                        started = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                        if elapsed > timeout_seconds:
                            stale_ids.append(r["id"])
                    except Exception:
                        stale_ids.append(r["id"])
                else:
                    stale_ids.append(r["id"])

            for sid in stale_ids:
                conn.execute(
                    "UPDATE analysis_jobs SET status = 'failed', error_message = 'Job timed out or abandoned by worker', completed_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, sid),
                )
            conn.execute("COMMIT;")
            return len(stale_ids)
        except Exception:
            conn.execute("ROLLBACK;")
            return 0

    # --------------------------------------------------------------------------
    # Incidents, Evidence, Detections Operations
    # --------------------------------------------------------------------------
    def finalize_analysis_results(
        self,
        job_id: str,
        incident_dict: Optional[Dict[str, Any]],
        evidence_list: List[Dict[str, Any]],
        detections_list: List[Dict[str, Any]],
        new_source: Optional[Dict[str, Any]] = None,
        new_job: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Transactionally commits analysis outputs:
        - Creates incident (if detections exist)
        - Inserts evidence keyframes
        - Inserts detections and junction links
        - Updates analysis_jobs to 'completed' with 100% progress
        Rolls back atomically on any failure!
        """
        conn = self.get_connection()
        conn.execute("BEGIN IMMEDIATE;")
        try:
            if new_source is not None:
                if new_job is None or incident_dict is None:
                    raise ValueError("Snapshot persistence requires source, job and incident")
                existing = self.get_incident(incident_dict["id"], new_source["user_id"])
                if existing:
                    conn.execute("COMMIT;")
                    return existing["id"]
                self.create_source(new_source)
                self.create_job(new_job)
            state = conn.execute("SELECT status, cancellation_requested, incident_id FROM analysis_jobs WHERE id=?", (job_id,)).fetchone()
            if state is None:
                raise ValueError("Cannot finalize a missing analysis job")
            if state["status"] not in ("queued", "processing"):
                conn.execute("COMMIT;")
                return state["incident_id"]
            if state["cancellation_requested"]:
                self.mark_job_cancelled(job_id)
                conn.execute("COMMIT;")
                return None
            incident_id = None
            now = datetime.now(timezone.utc).isoformat()

            if incident_dict:
                incident_id = incident_dict["id"]
                conn.execute("""
                INSERT INTO incidents (
                    id, source_id, job_id, user_id, title, channel, zone,
                    severity, reason, review_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    incident_id,
                    incident_dict["source_id"],
                    job_id,
                    incident_dict["user_id"],
                    incident_dict.get("title", "Tactical Threat Detection Event"),
                    incident_dict.get("channel", "Surveillance Node 1"),
                    incident_dict.get("zone", "Zone A"),
                    incident_dict.get("severity", "medium"),
                    incident_dict.get("reason", "Neural threat detection event"),
                    incident_dict.get("review_status", "unreviewed"),
                    incident_dict.get("created_at", now),
                    incident_dict.get("updated_at", now),
                ))

                # Insert evidence items
                for ev in evidence_list:
                    conn.execute("""
                    INSERT INTO evidence (
                        id, incident_id, source_id, user_id, evidence_type,
                        storage_bucket, storage_key, video_offset_seconds,
                        media_dimensions, image_data_url, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ev["id"],
                        incident_id,
                        ev["source_id"],
                        ev["user_id"],
                        ev.get("evidence_type", "key_frame"),
                        ev.get("storage_bucket", "evidence-frames"),
                        ev["storage_key"],
                        ev.get("video_offset_seconds"),
                        json.dumps(ev.get("media_dimensions")) if ev.get("media_dimensions") else None,
                        ev.get("image_data_url"),
                        ev.get("created_at", now),
                    ))

                # Insert detections and links
                for det in detections_list:
                    det_id = det["id"]
                    conn.execute("""
                    INSERT INTO detections (
                        id, job_id, source_id, evidence_id, class_id, class_name,
                        confidence, box, frame_index, video_offset_seconds, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        det_id,
                        job_id,
                        det["source_id"],
                        det.get("evidence_id"),
                        det["class_id"],
                        det["class_name"],
                        det["confidence"],
                        json.dumps(det["box"]),
                        det["frame_index"],
                        det["video_offset_seconds"],
                        det.get("created_at", now),
                    ))

                    conn.execute("""
                    INSERT OR IGNORE INTO incident_detection_links (incident_id, detection_id, created_at)
                    VALUES (?, ?, ?)
                    """, (incident_id, det_id, now))

            # Mark job complete
            conn.execute("""
            UPDATE analysis_jobs
            SET status = 'completed', progress = 100, incident_id = ?, completed_at = ?, updated_at = ?
            WHERE id = ?
            """, (incident_id, now, now, job_id))

            conn.execute("COMMIT;")
            return incident_id
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def get_incident(self, incident_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        query = "SELECT * FROM incidents WHERE id = ? AND is_deleted = 0"
        params: List[Any] = [incident_id]
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        if not row:
            return None

        evidence = conn.execute(
            "SELECT * FROM evidence WHERE incident_id = ? ORDER BY video_offset_seconds ASC", (incident_id,)).fetchall()
        detections = conn.execute("""SELECT d.* FROM detections d
            JOIN incident_detection_links l ON d.id = l.detection_id
            WHERE l.incident_id = ? ORDER BY d.confidence DESC""", (incident_id,)).fetchall()
        from ..services.security_response import response_status
        from .incident_view import incident_view
        return incident_view(row, evidence, detections, response_status(self, incident_id, user_id, row['review_status']))


    def append_automatic_evidence(self, incident_id, user_id, job_id, evidence, detections):
        """Bounded, owner-scoped, idempotent append; confirmed/dismissed captures stay frozen."""
        conn = self.get_connection()
        conn.execute('BEGIN IMMEDIATE')
        try:
            row = conn.execute("SELECT source_id,job_id,review_status,evidence_cleared FROM incidents WHERE id=? AND user_id=? AND is_deleted=0",(incident_id,user_id)).fetchone()
            duplicate = conn.execute('SELECT 1 FROM evidence WHERE id=?',(evidence['id'],)).fetchone()
            count = conn.execute('SELECT COUNT(*) FROM evidence WHERE incident_id=?',(incident_id,)).fetchone()[0]
            if row and row['job_id']==job_id and row['source_id']==evidence['source_id'] and row['review_status']=='unreviewed' and not row['evidence_cleared'] and not duplicate and count < 3:
                now = datetime.now(timezone.utc).isoformat()
                conn.execute("""INSERT INTO evidence(id,incident_id,source_id,user_id,storage_key,video_offset_seconds,media_dimensions,image_data_url,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""",(evidence['id'],incident_id,row['source_id'],user_id,evidence['storage_key'],evidence['video_offset_seconds'],json.dumps(evidence['media_dimensions']),evidence['image_data_url'],now))
                for d in detections:
                    conn.execute("""INSERT INTO detections(id,job_id,source_id,evidence_id,class_id,class_name,confidence,box,frame_index,video_offset_seconds,created_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(d['id'],job_id,row['source_id'],evidence['id'],d['class_id'],d['class_name'],d['confidence'],json.dumps(d['box']),d['frame_index'],d['video_offset_seconds'],now))
                    conn.execute('INSERT INTO incident_detection_links(incident_id,detection_id,created_at) VALUES(?,?,?)',(incident_id,d['id'],now))
                conn.execute('UPDATE incidents SET updated_at=? WHERE id=? AND user_id=?',(now,incident_id,user_id))
            conn.execute('COMMIT')
        except Exception:
            conn.execute('ROLLBACK')
            raise

    def list_incidents(
        self,
        user_id: str,
        status: Optional[str] = None,
        search_query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        created_after: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = self.get_connection()
        where_clauses = ["user_id = ?", "is_deleted = 0"]
        params: List[Any] = [user_id]

        if status:
            where_clauses.append("review_status = ?")
            params.append(status)

        if search_query:
            where_clauses.append("(title LIKE ? OR channel LIKE ? OR zone LIKE ? OR id LIKE ? OR source_id LIKE ? OR EXISTS (SELECT 1 FROM sources s WHERE s.id = incidents.source_id AND s.original_filename LIKE ?))")
            wild = f"%{search_query}%"
            params.extend([wild] * 6)
        if created_after:
            where_clauses.append("julianday(created_at) >= julianday(?)")
            params.append(created_after)

        where_sql = " AND ".join(where_clauses)

        # Count total items
        count_cursor = conn.execute(f"SELECT COUNT(*) as total FROM incidents WHERE {where_sql}", params)
        total_items = count_cursor.fetchone()["total"]

        # Pagination
        offset = max(0, (page - 1) * page_size)
        limit_params = params + [page_size, offset]

        cursor = conn.execute(
            f"SELECT id FROM incidents WHERE {where_sql} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            limit_params,
        )

        incident_ids = [r["id"] for r in cursor.fetchall()]
        items = []
        for inc_id in incident_ids:
            inc = self.get_incident(inc_id, user_id)
            if inc:
                items.append(inc)

        total_pages = max(1, (total_items + page_size - 1) // page_size)

        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
            },
        }

    def update_incident_review(
        self,
        incident_id: str,
        user_id: str,
        new_status: str,
        reviewer_id: Optional[str] = None,
        reviewer_notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute("""
        UPDATE incidents
        SET review_status = ?, reviewer_id = ?, reviewer_notes = ?, reviewed_at = ?, updated_at = ?
        WHERE id = ? AND user_id = ? AND is_deleted = 0
        """, (
            new_status,
            reviewer_id,
            reviewer_notes,
            now,
            now,
            incident_id,
            user_id,
        ))
        if cursor.rowcount == 0:
            return None
        return self.get_incident(incident_id, user_id)

    def dismiss_and_clear_evidence(self, incident_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Persist false-alarm review and hide captures atomically; raw records stay recoverable."""
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute("""
            UPDATE incidents SET review_status = 'dismissed', evidence_cleared = 1,
            reviewer_id = ?, reviewer_notes = 'False alarm dismissed; captures cleared from operator views.',
            reviewed_at = ?, updated_at = ? WHERE id = ? AND user_id = ? AND is_deleted = 0
        """, (user_id, now, now, incident_id, user_id))
        return self.get_incident(incident_id, user_id) if cursor.rowcount else None

    def soft_delete_incident(self, incident_id: str, user_id: str) -> bool:
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "UPDATE incidents SET is_deleted = 1, updated_at = ? WHERE id = ? AND user_id = ?",
            (now, incident_id, user_id),
        )
        return cursor.rowcount > 0

    # --------------------------------------------------------------------------
    # Audit Events Operations
    # --------------------------------------------------------------------------
    def record_audit_event(
        self,
        actor_id: Optional[str],
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        import uuid
        event_id = f"aud_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        conn = self.get_connection()
        conn.execute("""
        INSERT INTO audit_events (id, actor_id, action, resource_type, resource_id, request_id, metadata, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_id,
            actor_id,
            action,
            resource_type,
            resource_id,
            request_id,
            json.dumps(metadata or {}),
            now,
        ))
        return event_id

    # --------------------------------------------------------------------------
    # Dispatches & Revocation Operations
    # --------------------------------------------------------------------------
    def create_dispatch(self, dispatch_dict: Dict[str, Any]) -> Dict[str, Any]:
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
        INSERT INTO dispatches (
            id, incident_id, user_id, channel, destination_reference,
            provider, provider_reference, idempotency_key, status,
            is_simulated, failure_reason, attempt_count, delivered_at,
            cancelled_at, cancelled_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            dispatch_dict["id"],
            dispatch_dict["incident_id"],
            dispatch_dict["user_id"],
            dispatch_dict.get("channel", "telegram"),
            dispatch_dict.get("destination_reference", "authorized_destination"),
            dispatch_dict.get("provider", "simulated_provider"),
            dispatch_dict.get("provider_reference"),
            dispatch_dict.get("idempotency_key"),
            dispatch_dict.get("status", "pending"),
            1 if dispatch_dict.get("is_simulated") else 0,
            dispatch_dict.get("failure_reason"),
            dispatch_dict.get("attempt_count", 1),
            dispatch_dict.get("delivered_at"),
            dispatch_dict.get("cancelled_at"),
            dispatch_dict.get("cancelled_by"),
            dispatch_dict.get("created_at", now),
            dispatch_dict.get("updated_at", now),
        ))
        return self.get_dispatch(dispatch_dict["id"], dispatch_dict["user_id"])  # type: ignore

    def get_dispatch(self, dispatch_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        query = "SELECT * FROM dispatches WHERE id = ?"
        params: List[Any] = [dispatch_id]
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["incidentId"] = d["incident_id"]
        d["is_simulated"] = bool(d["is_simulated"])
        d["createdAt"] = d["created_at"]
        d["deliveredAt"] = d["delivered_at"]
        d["cancelledAt"] = d["cancelled_at"]
        d["failure_details"] = d.get("failure_reason")
        d["error"] = d.get("failure_reason")
        return d

    def get_dispatch_by_incident(self, incident_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        query = "SELECT * FROM dispatches WHERE incident_id = ? ORDER BY created_at DESC LIMIT 1"
        params: List[Any] = [incident_id]
        if user_id:
            query = "SELECT * FROM dispatches WHERE incident_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 1"
            params.append(user_id)
        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["incidentId"] = d["incident_id"]
        d["is_simulated"] = bool(d["is_simulated"])
        d["createdAt"] = d["created_at"]
        d["deliveredAt"] = d["delivered_at"]
        d["cancelledAt"] = d["cancelled_at"]
        d["failure_details"] = d.get("failure_reason")
        d["error"] = d.get("failure_reason")
        return d

    def get_dispatch_by_idempotency_key(self, idempotency_key: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        query = "SELECT * FROM dispatches WHERE idempotency_key = ?"
        params: List[Any] = [idempotency_key]
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["incidentId"] = d["incident_id"]
        d["is_simulated"] = bool(d["is_simulated"])
        d["createdAt"] = d["created_at"]
        d["deliveredAt"] = d["delivered_at"]
        d["cancelledAt"] = d["cancelled_at"]
        d["failure_details"] = d.get("failure_reason")
        d["error"] = d.get("failure_reason")
        return d

    def update_dispatch(self, dispatch_id: str, update_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat()
        set_clauses = ["updated_at = ?"]
        params = [now]
        for k, v in update_fields.items():
            if k == "is_simulated":
                v = 1 if v else 0
            set_clauses.append(f"{k} = ?")
            params.append(v)
        params.append(dispatch_id)
        conn.execute(f"UPDATE dispatches SET {', '.join(set_clauses)} WHERE id = ?", params)
        return self.get_dispatch(dispatch_id)

    def cancel_dispatch(self, dispatch_id: str, user_id: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Atomically cancels a pending dispatch if eligible.
        If already accepted or simulated, explains that message cannot be unsent.
        """
        conn = self.get_connection()
        conn.execute("BEGIN IMMEDIATE;")
        try:
            cursor = conn.execute("SELECT * FROM dispatches WHERE id = ? AND user_id = ?", (dispatch_id, user_id))
            row = cursor.fetchone()
            if not row:
                conn.execute("ROLLBACK;")
                return False, None, "Dispatch record not found or access denied."

            status = row["status"]
            if status == "cancelled":
                conn.execute("ROLLBACK;")
                return True, self.get_dispatch(dispatch_id), "Dispatch is already cancelled."

            if status in ("sent", "simulated"):
                conn.execute("ROLLBACK;")
                message = "Simulation is complete; no external notification was sent." if status == "simulated" else f"Notification already accepted by {row['provider']}; provider transmission cannot be retracted."
                return False, self.get_dispatch(dispatch_id), message

            if status == "failed":
                conn.execute("ROLLBACK;")
                return False, self.get_dispatch(dispatch_id), "Dispatch has already terminated with a failure state."

            now = datetime.now(timezone.utc).isoformat()
            conn.execute("""
            UPDATE dispatches
            SET status = 'cancelled', cancelled_at = ?, cancelled_by = ?, updated_at = ?
            WHERE id = ? AND status = 'pending'
            """, (now, user_id, now, dispatch_id))

            conn.execute("COMMIT;")
            return True, self.get_dispatch(dispatch_id), "Dispatch successfully revoked before provider transmission."
        except Exception as e:
            conn.execute("ROLLBACK;")
            logger.error("Error cancelling dispatch [%s]: %s", dispatch_id, e)
            return False, None, str(e)

    # --------------------------------------------------------------------------
    # Operator Security (PIN & Persistent Lockout)
    # --------------------------------------------------------------------------
    _PIN_ITERATIONS = 600_000

    def _hash_pin(self, user_id: str, pin: str) -> str:
        import secrets
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac('sha256', pin.encode('ascii'), salt, self._PIN_ITERATIONS)
        return f"pbkdf2_sha256${self._PIN_ITERATIONS}${salt.hex()}${digest.hex()}"

    def _valid_pin_hash(self, value: str) -> bool:
        import re
        return isinstance(value, str) and bool(re.fullmatch(r'pbkdf2_sha256\$600000\$[0-9a-f]{32}\$[0-9a-f]{64}', value))

    def has_operator_pin(self, user_id: str) -> bool:
        row = self.get_operator_security(user_id)
        return bool(row and self._valid_pin_hash(row['pin_hash']))

    def _write_pin(self, conn, user_id, pin):
        import re
        if not isinstance(pin, str) or not re.fullmatch(r'[0-9]{4,8}', pin):
            raise ValidationError('Choose a security PIN containing 4–8 digits.')
        conn.execute("""INSERT INTO operator_security(user_id,pin_hash,failed_attempts,locked_until,last_failed_at,updated_at)
            VALUES(?,?,0,NULL,NULL,?) ON CONFLICT(user_id) DO UPDATE SET pin_hash=excluded.pin_hash,
            failed_attempts=0,locked_until=NULL,last_failed_at=NULL,updated_at=excluded.updated_at""",
            (user_id, self._hash_pin(user_id, pin), datetime.now(timezone.utc).isoformat()))

    def set_operator_pin(self, user_id: str, pin: str) -> None:
        """Internal fixture/provisioning primitive. HTTP changes use configure_operator_pin."""
        self._write_pin(self.get_connection(), user_id, pin)

    def get_operator_security(self, user_id: str) -> Optional[Dict[str, Any]]:
        row = self.get_connection().execute('SELECT * FROM operator_security WHERE user_id=?', (user_id,)).fetchone()
        return dict(row) if row else None

    def configure_operator_pin(self, user_id: str, pin: str, current_pin: Optional[str] = None) -> None:
        conn = self.get_connection()
        conn.execute('BEGIN IMMEDIATE')
        try:
            row = conn.execute('SELECT * FROM operator_security WHERE user_id=?',(user_id,)).fetchone()
            if row and self._valid_pin_hash(row['pin_hash']):
                if not current_pin:
                    raise ValidationError('Enter your current security PIN before changing it.')
                self._verify_pin_locked(conn, row, current_pin, 3, 60)
            self._write_pin(conn, user_id, pin)
        except (ValidationError, LockedError):
            conn.execute('COMMIT')  # Keep failed-attempt accounting even when validation fails.
            raise
        except Exception:
            conn.execute('ROLLBACK')
            raise
        else:
            conn.execute('COMMIT')

    def _verify_pin_locked(self, conn, row, pin, max_attempts, lockout_seconds):
        import hmac
        now = datetime.now(timezone.utc)
        if not row or not self._valid_pin_hash(row['pin_hash']):
            raise ValidationError('Set your security PIN in Account settings before cancelling a dispatch.', details={'code':'PIN_SETUP_REQUIRED'})
        if row['locked_until']:
            lock_dt = datetime.fromisoformat(row['locked_until'])
            if lock_dt > now:
                raise LockedError('Operator PIN locked out. Please wait before trying again.', retry_after_seconds=max(1,int((lock_dt-now).total_seconds())))
        _, iterations, salt, expected = row['pin_hash'].split('$')
        candidate = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'), bytes.fromhex(salt), int(iterations)).hex()
        if hmac.compare_digest(candidate, expected):
            conn.execute('UPDATE operator_security SET failed_attempts=0,locked_until=NULL,updated_at=? WHERE user_id=?',(now.isoformat(),row['user_id']))
            return True
        failed = row['failed_attempts'] + 1
        locked_until = (now+timedelta(seconds=lockout_seconds)).isoformat() if failed >= max_attempts else None
        conn.execute('UPDATE operator_security SET failed_attempts=?,locked_until=?,last_failed_at=?,updated_at=? WHERE user_id=?',
            (failed,locked_until,now.isoformat(),now.isoformat(),row['user_id']))
        if locked_until:
            raise LockedError(f'Maximum failed PIN attempts reached ({max_attempts}). Security locked for {lockout_seconds} seconds.', retry_after_seconds=lockout_seconds)
        remaining = max_attempts-failed
        raise ValidationError(f"Invalid security PIN. {remaining} attempt{'s' if remaining != 1 else ''} remaining before lockout.", details={'attempts_remaining':remaining})

    def verify_operator_pin(self, user_id: str, pin: str, max_attempts: int = 3, lockout_seconds: int = 60) -> bool:
        """Never seeds credentials. Verification and attempt updates share an atomic write lock."""
        conn = self.get_connection()
        conn.execute('BEGIN IMMEDIATE')
        try:
            row = conn.execute('SELECT * FROM operator_security WHERE user_id=?',(user_id,)).fetchone()
            result = self._verify_pin_locked(conn, row, pin, max_attempts, lockout_seconds)
        except (ValidationError, LockedError):
            conn.execute('COMMIT')
            raise
        except Exception:
            conn.execute('ROLLBACK')
            raise
        else:
            conn.execute('COMMIT')
            return result
