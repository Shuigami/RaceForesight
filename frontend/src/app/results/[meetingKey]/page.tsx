import { MeetingSavesPage } from "@/components/MeetingSavesPage";

export default async function MeetingResultsPage({
  params,
}: {
  params: Promise<{ meetingKey: string }>;
}) {
  const { meetingKey } = await params;
  const key = Number(meetingKey);
  if (!Number.isFinite(key)) {
    return (
      <main className="mx-auto max-w-6xl px-5 py-10 text-sm text-fog">Invalid meeting.</main>
    );
  }
  return <MeetingSavesPage meetingKey={key} />;
}
