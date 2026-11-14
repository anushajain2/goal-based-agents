"use client";

import { Inbox } from "lucide-react";

import { ApprovalCard } from "@/components/ApprovalCard";
import { Card, Empty } from "@/components/ui";
import { useApi, UserRequest } from "@/lib/api";

export default function ApprovalsPage() {
  const { data, reload } = useApi<UserRequest[]>("/api/requests?status=pending");
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Approvals</h1>
        <p className="text-sm text-muted">
          Things the agent wants to do that need your OK, plus sign-ins and app connections it needs from you.
        </p>
      </div>
      {data && data.length === 0 && (
        <Card>
          <Empty icon={<Inbox size={36} />} title="Nothing waiting for you">
            When the agent wants to post, message, spend or change something you haven&apos;t pre-approved, it will ask here first.
          </Empty>
        </Card>
      )}
      {(data || []).map((r) => (
        <ApprovalCard key={r.id} req={r} onDone={reload} showCampaign />
      ))}
    </div>
  );
}
