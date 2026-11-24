import React from 'react';

interface CircularProgressRingProps {
  percentage: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
  color?: string;
}

export const CircularProgressRing: React.FC<CircularProgressRingProps> = ({
  percentage,
  size = 40,
  strokeWidth = 3.5,
  label,
  color,
}) => {
  const clamped = Math.min(100, Math.max(0, Math.round(percentage)));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (clamped / 100) * circumference;
  const strokeColor = color || (clamped >= 80 ? '#10b981' : clamped >= 60 ? '#f59e0b' : '#ef4444');

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        userSelect: 'none',
      }}
      title={`${clamped}% Confidence Score`}
    >
      <div
        style={{
          position: 'relative',
          width: size,
          height: size,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          style={{ transform: 'rotate(-90deg)' }}
        >
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke="#e2e8f0"
            strokeWidth={strokeWidth}
            fill="transparent"
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke={strokeColor}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            fill="transparent"
            style={{ transition: 'stroke-dashoffset 0.4s ease' }}
          />
        </svg>
        <span
          style={{
            position: 'absolute',
            fontSize: size > 44 ? '0.78rem' : '0.68rem',
            fontWeight: 700,
            color: strokeColor,
          }}
        >
          {clamped}%
        </span>
      </div>
      {label && (
        <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
          {label}
        </span>
      )}
    </div>
  );
};
