"use client";

import { ArrowLeft, Inbox } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { ApprovalCard, KIND_BADGE } from "@/components/ApprovalCard";
import { AgentAvatar } from "@/components/team";
import { Badge, Card, cx, Empty, PageHeader } from "@/components/ui";
import { OrgInfo, timeAgo, useApi, UserRequest } from "@/lib/api";

type Tab = "mine" | "all" | "done";

/** Everything AI employees need from people: approvals, questions, sign-ins. An inbox, not a feed. */
export default function Page() {
  return (
    <Suspense>
      <NeedsYouPage />
    </Suspense>
  );
}

function NeedsYouPage() {
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>("mine");
  const [selected, setSelected] = useState<string | null>(params.get("id"));
  const [mobileDetail, setMobileDetail] = useState(!!params.get("id"));
  const { data: org } = useApi<OrgInfo>("/api/org");
  const { data: mine, reload: reloadMine } = useApi<UserRequest[]>("/api/requests?status=pending&scope=mine");
  const { data: all, reload: reloadAll } = useApi<UserRequest[]>("/api/requests?status=pending&scope=all");
  const { data: approved, reload: reloadA } = useApi<UserRequest[]>("/api/requests?status=approved&scope=all&limit=30");
  const { data: rejected, reload: reloadR } = useApi<UserRequest[]>("/api/requests?status=rejected&scope=all&limit=30");
  const done = useMemo(() => [...(approved || []), ...(rejected || [])].sort((a, b) => (b.created_at > a.created_at ? 1 : -1)), [approved, rejected]);
  const list = tab === "mine" ? mine : tab === "all" ? all : done;
  const current = (list || []).find((r) => r.id === selected) || null;

  // A link to one request (?id=) that isn't for you: show it under the tab that has it.
  const linked = params.get("id");
  useEffect(() => {
    if (!linked || !mine || !all || mine.some((r) => r.id === linked)) return;
    if (all.some((r) => r.id === linked)) setTab("all");
    else if (done.some((r) => r.id === linked)) setTab("done");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linked, !!mine, !!all, done.length]);

  // Keep something selected: the first item, or the next one after deciding.
  useEffect(() => {
    // Hold on to a linked request while the lists load and the right tab opens.
    if (linked && selected === linked && !(list || []).some((r) => r.id === linked)
      && (!mine || !all || [...mine, ...all, ...done].some((r) => r.id === linked))) return;
    if (list && list.length && !list.some((r) => r.id === selected)) setSelected(list[0].id);
    if (list && !list.length) setSelected(null);
  }, [list, selected]);

  const reload = () => { reloadMine(); reloadAll(); reloadA(); reloadR(); };
  const counts = { mine: mine?.length ?? 0, all: all?.length ?? 0, done: done.length };
  const tabs: [Tab, string][] = [["mine", "For you"], ["all", `Everyone in ${org?.org.name || "the organization"}`], ["done", "Done"]];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Needs you"
        subtitle="Approvals, questions and suggestions waiting for a yes. Nothing happens until someone decides."
        actions={
          <div className="inline-flex rounded-xl bg-zinc-100 p-1 text-[13px] font-semibold">
            {tabs.map(([t, label]) => (
              <button key={t} onClick={() => { setTab(t); setMobileDetail(false); }}
                className={cx("rounded-lg px-3 py-1.5 transition", tab === t ? "bg-white text-ink shadow-sm" : "text-zinc-500 hover:text-ink")}>
                {t === "all" ? "Everyone" : label}{t !== "done" && counts[t] ? <span className={cx("tabular ml-1.5 rounded-full px-1.5 text-[11px]", tab === t ? "bg-amber-100 text-amber-800" : "bg-zinc-200 text-zinc-600")}>{counts[t]}</span> : null}
              </button>
            ))}
          </div>
        }
      />

      {list && list.length === 0 ? (
        <Card>
          <Empty icon={<Inbox size={36} />} title={tab === "done" ? "Nothing decided yet" : "You're all caught up"}>
            When an AI employee wants to send, post, spend or change something, or needs an answer only your team has, it shows up here.
          </Empty>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
          <Card className={cx("overflow-hidden", mobileDetail && "hidden lg:block")}>
            <ul className="max-h-[calc(100vh-220px)] divide-y divide-line overflow-y-auto">
              {(list || []).map((r) => {
                const k = KIND_BADGE[r.kind] || KIND_BADGE.action;
                return (
                  <li key={r.id}>
                    <button
                      onClick={() => { setSelected(r.id); setMobileDetail(true); }}
                      className={cx("flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-gray-50", r.id === selected && "bg-brand-50/70 hover:bg-brand-50")}
                    >
                      {r.agent_name ? <AgentAvatar name={r.agent_name} size={30} /> : <span className="h-[30px] w-[30px]" />}
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5">
                          <Badge tone={tab === "done" ? (r.status === "approved" ? "green" : "gray") : k.tone}>
                            {tab === "done" ? (r.status === "approved" ? (r.kind === "question" ? "Answered" : "Approved") : r.kind === "question" ? "Skipped" : "Declined") : k.label}
                          </Badge>
                          <span className="truncate text-[11.5px] text-muted">{r.agent_name}</span>
                        </span>
                        <span className="mt-1 line-clamp-2 block text-[13.5px] font-semibold leading-snug">{r.kind === "question" ? r.preview.question || r.title : r.title}</span>
                        <span className="mt-0.5 block truncate text-[11.5px] text-muted">
                          {r.campaign_name} · {timeAgo(r.created_at)}{tab === "all" && !r.routed_to_me ? ` · for ${r.approvers.join(", ")}` : ""}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </Card>

          <div className={cx(!mobileDetail && "hidden lg:block")}>
            {current ? (
              <Card className="p-5">
                <button onClick={() => setMobileDetail(false)} className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink lg:hidden"><ArrowLeft size={15} /> All requests</button>
                <ApprovalCard key={current.id} req={current} onDone={reload} detail />
                {current.campaign_name && (
                  <div className="mt-5 border-t border-line pt-3 text-sm">
                    <span className="text-muted">For the goal </span>
                    <Link href={`/goals/${current.campaign_id}`} className="font-semibold text-brand-600 hover:underline">{current.campaign_name}</Link>
                    {current.agent_id && <><span className="text-muted"> · </span><Link href={`/team/agents/${current.agent_id}`} className="text-brand-600 hover:underline">about {current.agent_name}</Link></>}
                  </div>
                )}
              </Card>
            ) : (
              <Card className="p-8 text-center text-sm text-muted">Pick something on the left.</Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
