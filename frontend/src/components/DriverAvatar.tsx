"use client";

import { useState } from "react";
import Image from "next/image";

type Props = {
  name: string;
  acronym: string;
  headshotUrl?: string | null;
  teamColour?: string | null;
  size?: number;
};

export function DriverAvatar({ name, acronym, headshotUrl, teamColour, size = 42 }: Props) {
  const [broken, setBroken] = useState(false);
  const colour = teamColour ? `#${teamColour}` : "#e10600";
  const showImage = Boolean(headshotUrl) && !broken;

  return (
    <span
      className="relative inline-flex shrink-0 bg-ink-850"
      style={{
        width: size,
        height: size,
        clipPath: "polygon(0 0, 100% 0, 100% 78%, 78% 100%, 0 100%)",
        boxShadow: `inset 3px 0 0 ${colour}`,
      }}
      aria-hidden={!showImage}
    >
      {showImage ? (
        <Image
          src={headshotUrl!}
          alt=""
          width={size}
          height={size}
          className="h-full w-full object-cover object-top"
          onError={() => setBroken(true)}
          unoptimized
        />
      ) : (
        <span
          className="flex h-full w-full items-center justify-center font-display text-[11px] tracking-wide text-fog"
          title={name}
        >
          {acronym.slice(0, 3)}
        </span>
      )}
    </span>
  );
}
