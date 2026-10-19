/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import type { Detection } from '../types/sightline.ts';

/**
 * SightLine AI - Model Classes & Detection Pipeline
 * The fine-tuned YOLO11n surveillance model strictly supports these 3 classes.
 * "gun" and "motion" are not supported by the model and must not be used.
 */
export const MODEL_CLASSES = ['person', 'mask', 'knife'] as const;

export type ModelClass = (typeof MODEL_CLASSES)[number];

export type DetectedObject = Detection;

/**
 * Extract detections from a video frame.
 * Currently returns an empty array until real backend inference is connected.
 */
export async function getDetections(
  _frame: string | ImageData | HTMLVideoElement
): Promise<Detection[]> {
  // TODO: Call backend inference endpoint (/api/detect or WebSocket) with the frame data
  return [];
}
