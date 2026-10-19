import type { SingleImageInferenceResponse } from '../../types/sightline.ts';

export function FrameDetectionOverlay({ result }: { result: SingleImageInferenceResponse }) {
  const { original_width: width, original_height: height, detections } = result;
  const fontSize = Math.max(14, width / 55);
  return (
    <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet" role="img" aria-label="Model predictions for the latest analyzed frame">
      {detections.map((detection, index) => {
        if (!detection.box) return null;
        const [x1, y1, x2, y2] = detection.box;
        const color = detection.classId === 'mask' ? '#fbbf24' : detection.classId === 'knife' ? '#fb7185' : '#4edea3';
        const label = `${detection.classId.toUpperCase()} ${Math.round(detection.confidence * 100)}%`;
        const labelWidth = label.length * fontSize * 0.65 + 12;
        const labelX = Math.max(0, Math.min(x1, width - labelWidth));
        const labelY = y1 < fontSize + 10 ? y1 : y1 - fontSize - 10;
        return (
          <g key={`${detection.classId}-${index}`} data-testid="frame-detection-box">
            <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1} fill="none" stroke={color} strokeWidth={Math.max(2, width / 400)} />
            <rect x={labelX} y={labelY} width={labelWidth} height={fontSize + 10} rx={3} fill={color} />
            <text x={labelX + 6} y={labelY + fontSize + 2} fontSize={fontSize} fontFamily="monospace" fontWeight="bold" fill="#051424">{label}</text>
          </g>
        );
      })}
    </svg>
  );
}
