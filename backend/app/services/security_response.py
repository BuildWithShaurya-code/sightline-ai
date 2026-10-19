"""Owner action journal. These records are not delivery or emergency-service acknowledgements."""
from datetime import datetime, timezone
from contextlib import nullcontext
from ..core.errors import NotFoundError, ValidationError

def response_status(db, incident_id, user_id, review_status=None):
    rows = db.get_connection().execute(
        "SELECT kind FROM response_events WHERE incident_id=? AND user_id=? ORDER BY seq DESC",
        (incident_id, user_id)).fetchall()
    return response_label((row['kind'] for row in rows), review_status)

def response_label(kinds, review_status=None):
    if review_status == 'dismissed':
        return 'False alarm'
    labels = {'resolved': 'Resolved', 'false_alarm': 'False alarm', 'contact_confirmed': 'Spoke to contact · confirmed by you',
              'summary_shared': 'Summary shared · confirmed by you', 'call_opened': 'Call opened', 'whatsapp_opened': 'WhatsApp opened'}
    recorded = set(kinds)
    for kind in ('false_alarm', 'resolved', 'contact_confirmed', 'summary_shared', 'call_opened', 'whatsapp_opened'):
        if kind in recorded:
            return labels[kind]
    return 'Not contacted'

def owned_status(db, incident_id, user_id):
    # Journal actions need ownership/status, not photos, detections or signed URLs.
    row = db.get_connection().execute(
        'SELECT review_status FROM incidents WHERE id=? AND user_id=? AND is_deleted=0',
        (incident_id, user_id)).fetchone()
    if not row:
        raise NotFoundError('Incident', incident_id)
    return row['review_status']

def get_response(db, incident_id, user_id):
    conn = db.get_connection()
    with conn.read_scope() if hasattr(conn, 'read_scope') else nullcontext():
        status = owned_status(db, incident_id, user_id)
        label = response_status(db, incident_id, user_id, status)
        events = conn.execute(
            "SELECT event_id AS id, kind, recipient, detail, created_at AS createdAt FROM response_events WHERE incident_id=? AND user_id=? ORDER BY seq DESC LIMIT 100",
            (incident_id, user_id)).fetchall()
        confirmed = conn.execute("SELECT DISTINCT recipient FROM response_events WHERE incident_id=? AND user_id=? AND kind='contact_confirmed'",(incident_id,user_id)).fetchall()
        return {'status': label, 'events': [dict(e) for e in reversed(events)], 'confirmedContacts': sorted(row['recipient'] for row in confirmed)}

def add_response(db, incident_id, user_id, action):
    conn = db.get_connection()
    conn.execute('BEGIN IMMEDIATE')
    try:
        review_status = owned_status(db, incident_id, user_id)
        prior = conn.execute('SELECT kind,recipient,detail FROM response_events WHERE incident_id=? AND user_id=? AND event_id=?',
                             (incident_id, user_id, action.eventId)).fetchone()
        if prior:
            if (prior['kind'], prior['recipient'], prior['detail']) != (action.kind, action.recipient, action.detail):
                raise ValidationError('Action key already used for another event')
        else:
            if action.kind in ('call_opened','whatsapp_opened','summary_shared','contact_confirmed','resolved') and review_status!='confirmed':
                raise ValidationError('Threat not confirmed. Confirm the threat before contacting police or security.')
            terminal = conn.execute("SELECT 1 FROM response_events WHERE incident_id=? AND user_id=? AND kind IN ('resolved','false_alarm') LIMIT 1", (incident_id,user_id)).fetchone()
            if (terminal or review_status == 'dismissed') and action.kind not in ('note',):
                raise ValidationError('This incident is closed; add a note or return to history')
            already_confirmed = action.kind in ('contact_confirmed','summary_shared') and conn.execute(
                'SELECT 1 FROM response_events WHERE incident_id=? AND user_id=? AND kind=? AND recipient=? LIMIT 1',
                (incident_id,user_id,action.kind,action.recipient)).fetchone()
            if already_confirmed:
                conn.execute('COMMIT')
                return get_response(db,incident_id,user_id)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute('INSERT INTO response_events(event_id,incident_id,user_id,kind,recipient,detail,created_at) VALUES(?,?,?,?,?,?,?)',
                         (action.eventId, incident_id, user_id, action.kind, action.recipient, action.detail, now))
            if action.kind == 'false_alarm':
                conn.execute("UPDATE incidents SET review_status='dismissed', evidence_cleared=1, reviewer_id=?, reviewer_notes=?, reviewed_at=?, updated_at=? WHERE id=? AND user_id=?",
                             (user_id, 'False alarm: '+action.detail, now, now, incident_id, user_id))
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise
    return get_response(db, incident_id, user_id)
