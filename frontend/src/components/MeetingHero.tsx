import { mediaUrl } from "@/lib/api";
import { CircuitThumb } from "./CircuitThumb";

type MeetingLike = {
  meeting_name: string;
  year?: number | null;
  circuit_short_name?: string | null;
  country_name?: string | null;
  circuit_image?: string | null;
  country_flag?: string | null;
  race_laps?: number | null;
};

type Props = {
  meeting: MeetingLike;
  kicker?: string;
  title?: string;
  meta?: string;
  children?: React.ReactNode;
  compact?: boolean;
};

export function MeetingHero({
  meeting,
  kicker,
  title,
  meta,
  children,
  compact = false,
}: Props) {
  const heading = title ?? meeting.meeting_name;
  const circuit = meeting.circuit_short_name || meeting.country_name || meeting.meeting_name;
  const trackSrc = mediaUrl(meeting.circuit_image);

  return (
    <div
      className="rf-fade-in relative isolate overflow-hidden border-y border-accent/40 bg-ink-850"
      style={{ clipPath: "polygon(0 0, 100% 0, 100% 88%, 97% 100%, 0 100%)" }}
    >
      <div className="pointer-events-none absolute left-0 top-0 h-full w-1.5 bg-accent" aria-hidden />
      {trackSrc && (
        <div className="pointer-events-none absolute inset-y-0 right-0 w-[55%] opacity-40 md:opacity-55">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={trackSrc}
            alt=""
            className="absolute inset-0 h-full w-full object-contain object-right pr-2 brightness-0 invert md:pr-6"
          />
          <div className="absolute inset-0 bg-gradient-to-r from-ink-850 via-ink-850/80 to-transparent" />
        </div>
      )}
      <div
        className={`relative flex flex-wrap items-center gap-4 ${
          compact ? "px-5 py-5 md:px-7" : "px-5 py-7 md:px-7 md:py-8"
        }`}
      >
        <CircuitThumb
          label={circuit || "GP"}
          circuitImage={trackSrc}
          countryFlag={meeting.country_flag}
          size={compact ? 64 : 88}
        />
        <div className="min-w-0 flex-1 space-y-1.5">
          {kicker && (
            <p className="text-[10px] uppercase tracking-[0.28em] text-accent">{kicker}</p>
          )}
          <p
            className={`font-display tracking-wide text-white ${
              compact ? "text-3xl md:text-4xl" : "text-3xl md:text-5xl"
            }`}
          >
            {heading}
          </p>
          {meta && <p className="font-mono text-xs text-fog">{meta}</p>}
          {children}
        </div>
      </div>
    </div>
  );
}
