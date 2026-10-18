import { Suspense } from "react";
import { RaceForesightApp } from "@/components/RaceForesightApp";

export default function Home() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-6xl px-5 py-16 text-sm text-muted md:px-8">Loading race…</main>
      }
    >
      <RaceForesightApp />
    </Suspense>
  );
}
