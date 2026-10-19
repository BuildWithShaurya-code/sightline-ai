from types import SimpleNamespace

from app.services.video_worker import VideoWorker


def candidates_with_rare_classes():
    frames = []
    for index in range(20):
        detections = [SimpleNamespace(classId='person', confidence=.9)]
        if index == 1:
            detections.append(SimpleNamespace(classId='mask', confidence=.7))
        if index == 13:
            detections.append(SimpleNamespace(classId='knife', confidence=.8))
        frames.append({'frame_index': index, 'time_seconds': index * .5, 'detections': detections})
    return frames


def test_rare_mask_and_knife_survive_bounded_evidence_selection():
    frames = candidates_with_rare_classes()
    worker = VideoWorker.__new__(VideoWorker)
    selected = worker._select_evidence_keyframes(frames)
    assert len(selected) == 8
    indices = [frame['frame_index'] for frame in selected]
    assert 1 in indices and 13 in indices
    assert indices == sorted(set(indices))
    assert {d.classId for frame in selected for d in frame['detections']} == {'person', 'mask', 'knife'}


def test_short_clip_keeps_all_detection_frames():
    frames = candidates_with_rare_classes()[:3]
    assert VideoWorker.__new__(VideoWorker)._select_evidence_keyframes(frames) == frames


def test_selects_strongest_mask_example():
    frames = candidates_with_rare_classes()
    frames[7]['detections'].append(SimpleNamespace(classId='mask', confidence=.95))
    selected = VideoWorker.__new__(VideoWorker)._select_evidence_keyframes(frames)
    assert any(frame['frame_index'] == 7 for frame in selected)
