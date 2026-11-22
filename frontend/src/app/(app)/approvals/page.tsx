"use client";

import { Inbox } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ApprovalCard } from "@/components/ApprovalCard";
import { Badge, Card, CardHeader, cx, Empty } from "@/components/ui";
import { OrgInfo, timeAgo, useApi, UserRequest } from "@/lib/api";

export default function NeedsYouPage() {
  const [scope, setScope] = useState<"mine" | "all">("mine");
  const { data: org } = useApi<OrgInfo>("/api/org");
  const { data, reload } = useApi<UserRequest[]>(`/api/requests?status=pending&scope=${scope}`);
  const { data: approved } = useApi<UserRequest[]>("/api/requests?status=approved&scope=all&limit=10");
  const { data: rejected } = useApi<UserRequest[]>("/api/requests?status=rejected&scope=all&limit=10");
  const recent = [...(approved || []), ...(rejected || [])].sort((a, b) => (b.created_at > a.created_at ? 1 : -1)).slice(0, 12);
  const myTeams = (org?.departments || []).filter((d) => org?.me.department_ids.includes(d.id)).map((d) => d.name);

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Needs you</h1>
        <p className="text-sm text-muted">
          When an AI employee needs a yes, it asks the people in its department.
          {myTeams.length > 0 && <> You approve for <b className="text-ink">{myTeams.join(", ")}</b>{org?.me.is_admin ? ", plus anything for teams with nobody in them" : ""}.</>}
        </p>
      </div>

      <div className="inline-flex overflow-hidden rounded-md border border-line text-xs font-semibold">
        {(["mine", "all"] as const).map((v) => (
          <button key={v} onClick={() => setScope(v)} className={cx("px-3 py-1.5", scope === v ? "bg-ink text-white" : "bg-white text-muted hover:text-ink")}>
            {v === "mine" ? "Routed to me" : `Everything in ${org?.org.name || "the organization"}`}
          </button>
        ))}
      </div>

      {data && data.length === 0 && (
        <Card>
          <Empty icon={<Inbox size={36} />} title={scope === "mine" ? "You're all caught up" : "Nothing is waiting on anyone"}>
            When an AI employee in your department wants to post, message, spend or change something that isn&apos;t pre-approved, it asks here.
          </Empty>
        </Card>
      )}
      {(data || []).map((r) => <ApprovalCard key={r.id} req={r} onDone={reload} showCampaign />)}

      {recent.length > 0 && (
        <Card>
          <CardHeader title="Recently decided" />
          <ul className="divide-y divide-line">
            {recent.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-[13px]">
                <Badge tone={r.status === "approved" ? "green" : "gray"}>{r.status === "approved" ? "Approved" : "Declined"}</Badge>
                <span className="min-w-0 flex-1 truncate">{r.title}</span>
                <span className="text-xs text-muted">
                  {r.decided_by_name ? `by ${r.decided_by_name}` : ""}{r.department_name ? ` · ${r.department_name}` : ""}
                </span>
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
