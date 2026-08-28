import type { FC } from 'react';

interface CompanyLogoBadgeProps {
  readonly companyId: string;
  readonly companyName: string;
  readonly size?: number;
  readonly className?: string;
}

// Procedural color hash for fallback logos
function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

export const CompanyLogoBadge: FC<CompanyLogoBadgeProps> = ({
  companyId,
  companyName,
  size = 22,
  className = '',
}) => {
  const normId = companyId.toLowerCase().replace(/[^a-z0-9]/g, '');

  // 1. Microsoft / Amesoft (4-Color Grid Logo)
  if (normId.includes('microsoft') || normId.includes('amesoft')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#f8fafc" stroke="#e2e8f0" strokeWidth="1" />
        <rect x="5" y="5" width="6.5" height="6.5" rx="1.5" fill="#f25022" />
        <rect x="12.5" y="5" width="6.5" height="6.5" rx="1.5" fill="#7fba00" />
        <rect x="5" y="12.5" width="6.5" height="6.5" rx="1.5" fill="#00a4ef" />
        <rect x="12.5" y="12.5" width="6.5" height="6.5" rx="1.5" fill="#ffb900" />
      </svg>
    );
  }

  // 2. Google (4-Color 'G' / Rainbow Arc)
  if (normId.includes('google')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#ffffff" stroke="#e2e8f0" strokeWidth="1" />
        <path
          d="M18.8 12.2c0-.6-.05-1.1-.15-1.6H12v3.1h3.8c-.16.9-.7 1.6-1.5 2.1v1.8h2.4c1.4-1.3 2.1-3.2 2.1-5.4z"
          fill="#4285f4"
        />
        <path
          d="M12 19c2 0 3.7-.7 4.9-1.8l-2.4-1.8c-.7.5-1.5.7-2.5.7-1.9 0-3.5-1.3-4.1-3H5.5v1.9C6.7 17.3 9.2 19 12 19z"
          fill="#34a853"
        />
        <path
          d="M7.9 13.1c-.15-.5-.25-1-.25-1.6 0-.6.1-1.1.25-1.6V8H5.5C5 9 4.7 10.1 4.7 11.5c0 1.4.3 2.5.8 3.5l2.4-1.9z"
          fill="#fbbc05"
        />
        <path
          d="M12 6.5c1.1 0 2.1.4 2.8 1.1l2.1-2.1C15.6 4.3 13.9 3.6 12 3.6 9.2 3.6 6.7 5.3 5.5 7.7l2.4 1.9c.6-1.8 2.2-3.1 4.1-3.1z"
          fill="#ea4335"
        />
      </svg>
    );
  }

  // 3. IBM (Striped Tech Logo)
  if (normId.includes('ibm')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#0062ff" />
        <rect x="4" y="6" width="16" height="1.8" fill="#ffffff" />
        <rect x="4" y="9.2" width="16" height="1.8" fill="#ffffff" />
        <rect x="4" y="12.4" width="16" height="1.8" fill="#ffffff" />
        <rect x="4" y="15.6" width="16" height="1.8" fill="#ffffff" />
        <text
          x="12"
          y="15.5"
          textAnchor="middle"
          fill="#0062ff"
          fontSize="7.5"
          fontWeight="900"
          fontFamily="system-ui, -apple-system, sans-serif"
          letterSpacing="0.8"
        >
          IBM
        </text>
      </svg>
    );
  }

  // 4. Telelvans / Tesla (Red Shield Emblem)
  if (normId.includes('telelvans') || normId.includes('tesla')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#dc2626" />
        <path
          d="M7 7.5C10 6.5 14 6.5 17 7.5l-1 2c-2.5-.8-5.5-.8-8 0l-1-2zM12 9.5c.8 0 1.5.2 2 .5L13 17.5h-2L10 10c.5-.3 1.2-.5 2-.5z"
          fill="#ffffff"
        />
      </svg>
    );
  }

  // 5. Healthcare / Serenex (Cyan & Emerald Leaf Cross)
  if (normId.includes('health') || normId.includes('serenex')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#0284c7" />
        <circle cx="12" cy="12" r="8.5" fill="#38bdf8" fillOpacity="0.3" />
        <path
          d="M10.5 6h3v4.5H18v3h-4.5V18h-3v-4.5H6v-3h4.5V6z"
          fill="#ffffff"
        />
      </svg>
    );
  }

  // 6. Veltrix / Itintier (Indigo Tech Prism)
  if (normId.includes('veltrix') || normId.includes('itintier')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#4338ca" />
        <path d="M12 4.5l6.5 3.8v7.4L12 19.5l-6.5-3.8V8.3L12 4.5z" fill="#6366f1" />
        <path d="M12 4.5l6.5 3.8L12 12 5.5 8.3 12 4.5z" fill="#818cf8" />
        <path d="M12 12v7.5l6.5-3.8V8.3L12 12z" fill="#4f46e5" />
      </svg>
    );
  }

  // 7. Kidartine (Ocean Blue Wave Capsule)
  if (normId.includes('kidartine')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#0284c7" />
        <rect x="4.5" y="8" width="15" height="8" rx="4" fill="#ffffff" fillOpacity="0.25" />
        <path
          d="M7 12c1.5-2 3.5-2 5 0s3.5 2 5 0"
          stroke="#ffffff"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    );
  }

  // 8. Coloetric (Cyan Layered Badge)
  if (normId.includes('coloetric')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#0891b2" />
        <rect x="5.5" y="6.5" width="13" height="11" rx="2.5" fill="#ffffff" />
        <rect x="7.5" y="9" width="9" height="6" rx="1.5" fill="#06b6d4" />
      </svg>
    );
  }

  // 9. Corporate (Multi-color Orbital Ring)
  if (normId.includes('corporate')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#ffffff" stroke="#e2e8f0" strokeWidth="1" />
        <circle cx="12" cy="12" r="7" stroke="#f97316" strokeWidth="2.2" strokeDasharray="9 4" />
        <circle cx="12" cy="12" r="4" fill="#8b5cf6" />
        <circle cx="12" cy="7" r="1.8" fill="#10b981" />
        <circle cx="16" cy="15" r="1.8" fill="#3b82f6" />
      </svg>
    );
  }

  // 10. Mireons (4-Color Diamond Prism)
  if (normId.includes('mireons')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#ffffff" stroke="#e2e8f0" strokeWidth="1" />
        <g transform="translate(12, 12) rotate(45) translate(-12, -12)">
          <rect x="6" y="6" width="5.5" height="5.5" rx="1" fill="#ec4899" />
          <rect x="12.5" y="6" width="5.5" height="5.5" rx="1" fill="#8b5cf6" />
          <rect x="6" y="12.5" width="5.5" height="5.5" rx="1" fill="#06b6d4" />
          <rect x="12.5" y="12.5" width="5.5" height="5.5" rx="1" fill="#f59e0b" />
        </g>
      </svg>
    );
  }

  // 11. Uber / Altiven (Dark Minimalist Tile)
  if (normId.includes('uber') || normId.includes('altiven')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#18181b" />
        <rect x="6" y="6" width="12" height="12" rx="3" stroke="#22c55e" strokeWidth="1.8" />
        <circle cx="12" cy="12" r="2.5" fill="#ffffff" />
      </svg>
    );
  }

  // 12. KBM (Navy & Gold Geometric Emblem)
  if (normId.includes('kbm')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#1e3a8a" />
        <path d="M7 6h3v4.5L14 6h3.5l-4.5 5.5L18 18h-3.5l-4.5-6.5V18H7V6z" fill="#f59e0b" />
      </svg>
    );
  }

  // 13. Pixy (Indigo Starburst)
  if (normId.includes('pixy')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#065f46" />
        <circle cx="12" cy="12" r="6" fill="#10b981" />
        <path d="M12 4v16M4 12h16" stroke="#ec4899" strokeWidth="2" strokeLinecap="round" />
        <circle cx="12" cy="12" r="2.5" fill="#ffffff" />
      </svg>
    );
  }

  // 14. Primeforge (Industrial Forge Hex)
  if (normId.includes('primeforge')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#c2410c" />
        <path d="M12 5l6 3.5v7L12 19l-6-3.5v-7L12 5z" fill="#ea580c" stroke="#fed7aa" strokeWidth="1.2" />
        <circle cx="12" cy="12" r="3" fill="#ffffff" />
      </svg>
    );
  }

  // 15. Corevia Tech (Neural Node Grid)
  if (normId.includes('corevia')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#312e81" />
        <circle cx="8" cy="8" r="2" fill="#38bdf8" />
        <circle cx="16" cy="8" r="2" fill="#818cf8" />
        <circle cx="12" cy="16" r="2.5" fill="#a78bfa" />
        <path d="M8 8l4 8 4-8H8z" stroke="#38bdf8" strokeWidth="1" fill="none" opacity="0.6" />
      </svg>
    );
  }

  // 16. Meridian Logic (Quantum Radar / Compass)
  if (normId.includes('meridian')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#064e3b" />
        <circle cx="12" cy="12" r="7" stroke="#34d399" strokeWidth="1.5" fill="none" />
        <circle cx="12" cy="12" r="3.5" stroke="#a7f3d0" strokeWidth="1.2" fill="none" />
        <path d="M12 5v14M5 12h14" stroke="#10b981" strokeWidth="1" strokeDasharray="2 2" />
      </svg>
    );
  }

  // 17. Northstar Materials (Sapphire Compass Star)
  if (normId.includes('northstar')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#1e1b4b" />
        <path
          d="M12 4l2.5 5.5L20 12l-5.5 2.5L12 20l-2.5-5.5L4 12l5.5-2.5L12 4z"
          fill="#38bdf8"
        />
        <circle cx="12" cy="12" r="2" fill="#ffffff" />
      </svg>
    );
  }

  // 18. Bistelligence (Emerald & Gold AI Prism)
  if (normId.includes('bistelligence')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#107c41" />
        <polygon points="12,5 18,12 12,19 6,12" fill="#22c55e" />
        <polygon points="12,7 16,12 12,17 8,12" fill="#facc15" />
        <circle cx="12" cy="12" r="2" fill="#ffffff" />
      </svg>
    );
  }

  // 19. Lumena AI (Radiant Gold Sunburst)
  if (normId.includes('lumena')) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={`company-custom-logo-svg ${className}`}
        style={{ borderRadius: '5px', flexShrink: 0 }}
      >
        <rect width="24" height="24" rx="5" fill="#78350f" />
        <circle cx="12" cy="12" r="5" fill="#f59e0b" />
        <path
          d="M12 3v3M12 18v3M3 12h3M18 12h3M5.5 5.5l2.2 2.2M16.3 16.3l2.2 2.2M5.5 18.5l2.2-2.2M16.3 7.7l2.2-2.2"
          stroke="#fde68a"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    );
  }

  // Procedural Fallback Vector Logo based on String Hash
  const hash = hashString(normId || companyName);
  const palette = [
    { bg: '#2563eb', acc1: '#60a5fa', acc2: '#93c5fd' },
    { bg: '#059669', acc1: '#34d399', acc2: '#a7f3d0' },
    { bg: '#7c3aed', acc1: '#a78bfa', acc2: '#ddd6fe' },
    { bg: '#d97706', acc1: '#fbbf24', acc2: '#fef3c7' },
    { bg: '#e11d48', acc1: '#fb7185', acc2: '#fecdd3' },
    { bg: '#0891b2', acc1: '#38bdf8', acc2: '#bae6fd' },
  ];
  const color = palette[hash % palette.length];
  const shapeMode = hash % 3;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={`company-custom-logo-svg ${className}`}
      style={{ borderRadius: '5px', flexShrink: 0 }}
    >
      <rect width="24" height="24" rx="5" fill={color.bg} />
      {shapeMode === 0 && (
        <>
          <circle cx="12" cy="12" r="6" fill={color.acc1} />
          <polygon points="12,8 15,14 9,14" fill={color.acc2} />
        </>
      )}
      {shapeMode === 1 && (
        <>
          <rect x="7" y="7" width="10" height="10" rx="2" fill={color.acc1} />
          <circle cx="12" cy="12" r="2.5" fill="#ffffff" />
        </>
      )}
      {shapeMode === 2 && (
        <>
          <path d="M7 16L12 8L17 16H7Z" fill={color.acc1} />
          <circle cx="12" cy="14" r="1.8" fill={color.acc2} />
        </>
      )}
    </svg>
  );
};
