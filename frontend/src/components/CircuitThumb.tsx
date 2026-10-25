"use client";

import { useEffect, useState } from "react";
import { mediaUrl } from "@/lib/api";

type Props = {
  label: string;
  circuitImage?: string | null;
  countryFlag?: string | null;
  size?: number;
  className?: string;
};

export function CircuitThumb({
  label,
  circuitImage,
  size = 56,
  className = "",
}: Props) {
  const src = mediaUrl(circuitImage);
  const [broken, setBroken] = useState(false);

  useEffect(() => {
    setBroken(false);
  }, [src]);

  const show = Boolean(src) && !broken;

  return (
    <span
      className={`relative inline-flex shrink-0 items-center justify-center bg-ink-850 ${className}`}
      style={{
        width: size,
        height: size,
        clipPath: "polygon(8% 0, 100% 0, 92% 100%, 0 100%)",
        boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.12)",
      }}
      title={label}
      aria-hidden
    >
      {show ? (
        // eslint-disable-next-line @next/next/no-img-element -- F1 CDN URLs with mixed encoding; img is reliable
        <img
          src={src!}
          alt=""
          width={size}
          height={size}
          className="h-full w-full object-contain p-2 brightness-0 invert opacity-90"
          onError={() => setBroken(true)}
        />
      ) : (
        <span className="px-1 text-center font-mono text-[9px] uppercase leading-tight tracking-wide text-muted">
          {label}
        </span>
      )}
    </span>
  );
}
