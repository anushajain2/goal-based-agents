"use client";

import { ArrowLeft, Inbox } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState, useRef } from "react";

import { ApprovalCard, KIND_BADGE } from "@/components/ApprovalCard";
import { EmployeeAvatar } from "@/components/Shell";
import { Badge, Card, cx, Empty, PageHeader } from "@/components/ui";
import { OrgInfo, timeAgo, useApi, UserRequest } from "@/lib/api";

type Tab = "mine" | "all" | "done";

/** Everything Autopilot needs from people: approvals, questions, sign-ins. An inbox, not a feed. */
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
  const placed = useRef(false);  // only on arrival: deciding it later must not jump to another tab
  const shown = useRef(false);
  useEffect(() => {
    if (placed.current || !linked || !mine || !all) return;
    if (!mine.some((r) => r.id === linked)) {
      if (all.some((r) => r.id === linked)) setTab("all");
      else if (done.some((r) => r.id === linked)) setTab("done");
      else if (!approved || !rejected) return;  // the done lists are still loading
    }
    placed.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linked, !!mine, !!all, done.length]);

  // Keep something selected: the first item, or the next one after deciding.
  useEffect(() => {
    // Hold on to a linked request while the lists load and the right tab opens (once).
    if (linked && !shown.current) {
      if ((list || []).some((r) => r.id === linked)) shown.current = true;
      else if (selected === linked && (!mine || !all || [...mine, ...all, ...done].some((r) => r.id === linked))) return;
    }
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
        subtitle="Autopilot shows its work here. Anything that needs a yes waits for one; heads-ups go ahead unless you stop them."
        actions={
          <div className="inline-flex rounded-xl bg-stone-100 p-1 text-[13px] font-semibold">
            {tabs.map(([t, label]) => (
              <button key={t} onClick={() => { setTab(t); setMobileDetail(false); }}
                className={cx("rounded-lg px-3 py-1.5 transition", tab === t ? "bg-white text-ink shadow-sm" : "text-stone-500 hover:text-ink")}>
                {t === "all" ? "Everyone" : label}{t !== "done" && counts[t] ? <span className={cx("tabular ml-1.5 rounded-full px-1.5 text-[11px]", tab === t ? "bg-brand-50 text-brand-700" : "bg-stone-200 text-stone-600")}>{counts[t]}</span> : null}
              </button>
            ))}
          </div>
        }
      />

      {list && list.length === 0 ? (
        <Card>
          <Empty icon={<Inbox size={36} />} title={tab === "done" ? "Nothing decided yet" : "You're all caught up"}>
            When Autopilot wants to send, post, spend or change something, or needs an answer only your team has, it shows up here.
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
                      className={cx("flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-stone-50", r.id === selected && "bg-brand-50/70 hover:bg-brand-50")}
                    >
                      <EmployeeAvatar size={30} />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5">
                          <Badge tone={tab === "done" ? (r.status === "approved" ? "green" : "gray") : k.tone}>
                            {tab === "done"
                              ? (r.auto_approve_at ? (r.status === "approved" ? "Went ahead" : "Stopped")
                                : r.status === "approved" ? (r.kind === "question" ? "Answered" : "Approved") : r.kind === "question" ? "Skipped" : "Declined")
                              : r.auto_approve_at ? "Heads-up" : k.label}
                          </Badge>
                          <span className="truncate text-[11.5px] text-muted">{r.department_name}</span>
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
                    {current.department_name && <><span className="text-muted"> · </span><Link href="/team" className="text-brand-600 hover:underline">{current.department_name} team</Link></>}
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
