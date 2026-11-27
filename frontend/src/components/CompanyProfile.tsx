"use client";

import { ExternalLink } from "lucide-react";
import { ReactNode } from "react";

import { CompanyProfile } from "@/lib/api";
import { Badge, Card } from "./ui";

const FACTS: [keyof CompanyProfile, string][] = [
  ["offering", "What you sell"], ["customers", "Who you sell to"], ["business_model", "Business model"], ["stage", "Stage"],
  ["funding", "Funding"], ["revenue", "Revenue"], ["team", "Team"], ["traction", "Traction"],
];

export function CompanyProfileCard({ profile, name, action }: { profile: CompanyProfile; name: string; action?: ReactNode }) {
  const facts = FACTS.filter(([k]) => typeof profile[k] === "string" && (profile[k] as string).trim() && (profile[k] as string).toLowerCase() !== "unknown");
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="text-xs font-semibold text-muted">What we learned about {name}</div>
        {action}
      </div>
      <p className="mt-1.5 text-[15px] leading-relaxed">{profile.summary}</p>
      {facts.length > 0 && (
        <dl className="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          {facts.map(([k, label]) => (
            <div key={k}>
              <dt className="text-xs font-semibold text-muted">{label}</dt>
              <dd className="mt-0.5">{profile[k] as string}</dd>
            </div>
          ))}
        </dl>
      )}
      {(profile.current_focus?.length || 0) > 0 && (
        <div className="mt-4">
          <div className="mb-1.5 text-xs font-semibold text-muted">Looks like you&apos;re focused on</div>
          <div className="flex flex-wrap gap-1.5">{profile.current_focus.map((f) => <Badge key={f} tone="blue">{f}</Badge>)}</div>
        </div>
      )}
      {(profile.sources?.length || 0) > 0 && (
        <details className="mt-4 text-xs">
          <summary className="cursor-pointer font-semibold text-muted">Sources ({profile.sources!.length})</summary>
          <ul className="mt-2 space-y-1">
            {profile.sources!.map((s) => (
              <li key={s.url}>
                <a href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-brand-600 hover:underline">
                  <ExternalLink size={11} /> {s.title}
                </a>
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="mt-4 text-xs text-muted">Something wrong? Each goal&apos;s brief starts from this; edit it on the goal&apos;s Settings tab.</p>
    </Card>
  );
}

