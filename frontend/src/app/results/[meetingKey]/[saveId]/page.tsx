import { SaveComparePage } from "@/components/SaveComparePage";

export default async function SaveResultsPage({
  params,
}: {
  params: Promise<{ meetingKey: string; saveId: string }>;
}) {
  const { meetingKey, saveId } = await params;
  const key = Number(meetingKey);
  if (!Number.isFinite(key) || !saveId) {
    return (
      <main className="mx-auto max-w-6xl px-5 py-10 text-sm text-fog">Invalid save.</main>
    );
  }
  return <SaveComparePage meetingKey={key} saveId={saveId} />;
}
