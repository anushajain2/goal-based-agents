"use client";

import { Inbox } from "lucide-react";
import Link from "next/link";

import { ApprovalCard } from "@/components/ApprovalCard";
import { Badge, Card, CardHeader, Empty } from "@/components/ui";
import { timeAgo, useApi, UserRequest } from "@/lib/api";

export default function NeedsYouPage() {
  const { data, reload } = useApi<UserRequest[]>("/api/requests?status=pending");
  const { data: recentApproved } = useApi<UserRequest[]>("/api/requests?status=approved&limit=10");
  const { data: recentRejected } = useApi<UserRequest[]>("/api/requests?status=rejected&limit=10");
  const recent = [...(recentApproved || []), ...(recentRejected || [])]
    .sort((a, b) => (b.created_at > a.created_at ? 1 : -1))
    .slice(0, 12);

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Needs you</h1>
        <p className="text-sm text-muted">
          What Autopilot wants to do that needs your OK, plus sign-ins and app connections only you can do. Tick &quot;don&apos;t ask me next time&quot; to
          let it handle that kind of thing on its own from now on.
        </p>
      </div>
      {data && data.length === 0 && (
        <Card>
          <Empty icon={<Inbox size={36} />} title="You're all caught up">
            When Autopilot wants to post, message, spend or change something you haven&apos;t pre-approved, it asks here first.
          </Empty>
        </Card>
      )}
      {(data || []).map((r) => <ApprovalCard key={r.id} req={r} onDone={reload} showCampaign />)}

      {recent.length > 0 && (
        <Card>
          <CardHeader title="Recently decided" />
          <ul className="divide-y divide-line">
            {recent.map((r) => (
              <li key={r.id} className="flex items-center gap-3 px-4 py-2.5 text-[13px]">
                <Badge tone={r.status === "approved" ? "green" : "gray"}>{r.status === "approved" ? "Approved" : "Declined"}</Badge>
                <span className="min-w-0 flex-1 truncate">{r.title}</span>
                {r.campaign_name && <Link href={`/goals/${r.campaign_id}`} className="shrink-0 text-xs text-brand-600 hover:underline">{r.campaign_name}</Link>}
                <span className="shrink-0 text-xs text-muted">{timeAgo(r.created_at)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
