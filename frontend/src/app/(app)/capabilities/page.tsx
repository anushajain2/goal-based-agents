"use client";

import { CheckCircle2, Eye, Hand, Search, Wallet } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { GoalPanel } from "@/components/GoalPanel";
import { Opportunities } from "@/components/Opportunities";
import { StartGoal } from "@/components/StartGoal";
import { UseCaseLibrary } from "@/components/UseCaseLibrary";
import { Campaign, OrgInfo, useApi } from "@/lib/api";
import { USE_CASES } from "@/lib/useCases";

export default function CapabilitiesPage() {
  const router = useRouter();
  const { data: org, reload: reloadOrg } = useApi<OrgInfo>("/api/org");
  const { data: goals, reload } = useApi<Campaign[]>("/api/campaigns");
  const [panel, setPanel] = useState<Campaign | null>(null);
  const [starting, setStarting] = useState<Campaign[] | null>(null);
  const found = org?.org.profile?.opportunities;
  const recommended = !!found && found.findings.length > 0;
  const refresh = () => { reload(); reloadOrg(); };

  return (
    <div className="space-y-8">
      <div className="max-w-3xl">
        <h1 className="text-2xl font-bold">Goal ideas</h1>
        <p className="mt-1 text-sm text-muted">
          {recommended
            ? `What we found ${org!.org.name} is missing out on, with the goal that fixes each, and more ideas below.`
            : "Goals founders and agencies use Autopilot for. Pick one to set it up; you can change everything before it starts."}
        </p>
      </div>

      {recommended && (
        <section className="space-y-3">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-bold"><Search size={18} className="text-brand-600" /> Recommended for {org!.org.name}</h2>
            <p className="text-sm text-muted">
              From the check we ran{found!.scanned_at ? ` on ${new Date(found!.scanned_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}` : ""}.
              Nothing runs, and nothing is spent, until you turn a goal on.
            </p>
          </div>
          <Opportunities profile={org!.org.profile} org={org} goals={goals} orgName={org!.org.name} canStart
            onStart={setStarting} onOpen={setPanel} titled={false} />
        </section>
      )}

      <section className="space-y-4">
        {recommended && (
          <div>
            <h2 className="text-lg font-bold">More ideas</h2>
            <p className="text-sm text-muted">{USE_CASES.length} goals Autopilot works well on, across sales, marketing, research, fundraising, hiring and more.</p>
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <How icon={<CheckCircle2 size={18} />} title="You set the finish line" text="Each goal says exactly when a result counts, so you can judge the work." />
          <How icon={<Wallet size={18} />} title="It stays within budget" text="A hard spending limit, with the cost of every work session shown." />
          <How icon={<Hand size={18} />} title="It asks first" text="Posting, messaging and spending wait for your OK until you say otherwise." />
          <How icon={<Eye size={18} />} title="You see everything" text="Every plan, step, action and decision is in the work log." />
        </div>
        <UseCaseLibrary onPick={(u) => router.push(`/goals/new?uc=${u.id}`)} onCustom={() => router.push("/goals/new")} />
      </section>

      {panel && <GoalPanel goal={panel} onClose={() => setPanel(null)} onStart={(g) => { setPanel(null); setStarting([g]); }} onRemoved={() => { setPanel(null); refresh(); }} />}
      {starting && <StartGoal goals={starting} onClose={() => setStarting(null)} onStarted={() => { setStarting(null); refresh(); }} />}
    </div>
  );
}

function How({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return (
    <div className="rounded-xl border border-line bg-white p-4">
      <div className="text-brand-600">{icon}</div>
      <div className="mt-2 text-[13.5px] font-semibold">{title}</div>
      <div className="mt-0.5 text-xs text-muted">{text}</div>
    </div>
  );
}
