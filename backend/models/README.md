# SightLine AI - Neural Model Checkpoint Directory

This directory holds the fine-tuned physical threat detection model checkpoint.

## Model Metadata

| Attribute | Value |
| :--- | :--- |
| **Model Filename** | `best.pt` (referenced from fine-tuned checkpoint archive `best.zip`) |
| **Checkpoint Size** | 5,451,802 bytes (5.20 MB) |
| **SHA256 Checksum** | `0b17d4a5f108447e277dce5688ecd1d3924a43792f2d751c018858d9539dc0f8` |
| **Model Architecture** | `DetectionModel` (Ultralytics YOLO11 nano) |
| **Trained Classes (Exact)** | `0: person`, `1: mask`, `2: knife` |
| **Forbidden / Non-existent Classes** | `gun`, `motion` (completely absent; do not add) |
| **Framework Version** | PyTorch 2.14.1, Ultralytics 8.4.135 (tested on 8.4.178) |
| **Checkpoint Epoch** | 200 (best fitness achieved) |
| **Checkpoint Timestamp** | `2026-08-30T11:40:21.631690+00:00` |

## Checkpoint Handling Rules

1. **PyTorch Zip Archive**: `best.zip` is a standard PyTorch serialized model archive containing `best/data.pkl` and parameter tensor segments. It is preserved byte-for-byte and exposed as `best.pt`.
2. **Never Treat `data.pkl` Alone as Model**: PyTorch checkpoints require the full zip container with storage alignment and tensor buffers.
3. **No Retraining or Generic Weights**: Do not substitute generic YOLO weights (e.g. COCO 80-class `yolo11n.pt`).
4. **Decoupled Architecture**: In Phase 1, the FastAPI API server performs lightweight checkpoint verification via `backend/app/services/model_checker.py` without keeping heavy neural inference tensors in memory. Heavy continuous inference is isolated to an asynchronous inference worker in Phase 2.
