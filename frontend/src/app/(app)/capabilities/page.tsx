"use client";

import { CheckCircle2, Eye, Hand, Wallet } from "lucide-react";
import { useRouter } from "next/navigation";

import { EmployeeAvatar } from "@/components/Shell";
import { UseCaseLibrary } from "@/components/UseCaseLibrary";
import { USE_CASES } from "@/lib/useCases";

export default function CapabilitiesPage() {
  const router = useRouter();
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start gap-4">
        <EmployeeAvatar size={48} />
        <div className="max-w-3xl flex-1">
          <h1 className="text-2xl font-bold">What Autopilot can do</h1>
          <p className="mt-1 text-sm text-muted">
            {USE_CASES.length} goals founders and agencies hire it for, across sales, marketing, research, fundraising, hiring and more. It works best on
            goals with a countable finish line. Pick one to set it up; you can change everything before it starts.
          </p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <How icon={<CheckCircle2 size={18} />} title="You set the finish line" text="Each goal says exactly when a result counts, so you can judge the work." />
        <How icon={<Wallet size={18} />} title="It stays within budget" text="A hard spending limit, with the cost of every work session shown." />
        <How icon={<Hand size={18} />} title="It asks first" text="Posting, messaging and spending wait for your OK until you say otherwise." />
        <How icon={<Eye size={18} />} title="You see everything" text="Every plan, step, action and decision is in the work log." />
      </div>

      <UseCaseLibrary onPick={(u) => router.push(`/goals/new?uc=${u.id}`)} onCustom={() => router.push("/goals/new")} />
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
