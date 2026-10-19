# SightLine model card

## Identity

- Architecture: fine-tuned Ultralytics YOLO11 nano `DetectionModel`.
- Exact model class map: `0: person`, `1: mask`, `2: knife`.
- Private checkpoint: `backend/models/best.pt`.
- SHA-256: `0b17d4a5f108447e277dce5688ecd1d3924a43792f2d751c018858d9539dc0f8`.
- Current runtime: PyTorch 2.14.1 and Ultralytics 8.4.178, declared in backend requirements.

## Intended use

Assist a human operator in finding and reviewing candidate frames in consented video or camera input. A detected person, mask or knife is not an identity, intention or theft determination. Human review is required before response actions. The app is not an autonomous emergency service.

Default inference/evidence confidence is 0.25; the browser mask warning/siren gate is at least 0.60. These thresholds serve different purposes and do not constitute a calibrated probability of crime. The model has no gun class, face-recognition identity or general action-understanding capability.

## Evaluation status

Local functional checks exercised person/mask examples, negative scenes, boxes/dimensions, real video processing and restart behavior. Representative positive knife detection, class-wise precision/recall, false alerts per hour, lighting/occlusion tests and end-to-end latency remain unmeasured in the current record. Do not substitute test counts for model quality metrics.

Before an accuracy claim, use a consented labelled evaluation set separated from training. Report sample counts, class balance, confidence threshold, matching/IoU rules, misses/false alerts, hardware and full pipeline latency. Record model hash and dataset version for each run. No live footage or labels were published by this work.

## Provenance and permissions still needed

Training dataset source/permissions, split counts, annotation methods, training configuration, model-author attribution and distribution license have not been verified from the available handoff. The checkpoint’s embedded metadata alone does not establish these facts. The owner must supply the missing provenance and decide an appropriate release policy before public distribution. Preserve weights; do not retrain or swap a generic model to bypass these gaps.
