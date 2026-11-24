interface BrandMarkProps {
  size?: number;
}

export default function BrandMark({ size = 40 }: BrandMarkProps) {
  return (
    <svg
      className="brand-mark"
      width={size}
      height={size}
      viewBox="0 0 40 40"
      role="img"
      aria-label="IntelliStock logo"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="intellistock-brand-gradient" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#70d6ff" />
          <stop offset="100%" stopColor="#7c5cff" />
        </linearGradient>
      </defs>
      <rect x="0.5" y="0.5" width="39" height="39" rx="12" fill="url(#intellistock-brand-gradient)" />
      <text
        x="20"
        y="26"
        textAnchor="middle"
        fontFamily="Inter, Segoe UI, sans-serif"
        fontSize="16"
        fontWeight="800"
        letterSpacing="-1.2"
        fill="#08131d"
      >
        mj
      </text>
    </svg>
  );
}
