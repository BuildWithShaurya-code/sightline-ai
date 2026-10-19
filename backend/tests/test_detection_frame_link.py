from app.schemas.incident import IncidentSchema


def test_incident_response_preserves_evidence_link_and_timestamp():
    """FastAPI response serialization must not strip the frame identity used by overlays."""
    payload = {
        'id': 'INC-FRAME-LINK',
        'sourceId': 'source-test',
        'createdAt': '2026-10-16T00:00:00Z',
        'status': 'unreviewed',
        'frames': [
            {'id': 'ev-first', 'timeSeconds': 0, 'imageDataUrl': 'data:image/jpeg;base64,test'},
            {'id': 'ev-second', 'timeSeconds': 1, 'imageDataUrl': 'data:image/jpeg;base64,test'},
        ],
        'detections': [{
            'classId': 'mask', 'confidence': .52, 'box': [0, 1, 89, 145],
            'evidence_id': 'ev-second', 'video_offset_seconds': 1.0, 'frame_index': 30,
        }],
    }
    data = IncidentSchema.model_validate(payload).model_dump(mode='json')
    prediction = data['detections'][0]
    assert prediction['evidence_id'] == data['frames'][1]['id']
    assert prediction['video_offset_seconds'] == 1.0
    assert prediction['frame_index'] == 30
