"use client";

import {
  ArrowRight,
  BarChart3,
  Building2,
  Code2,
  Gauge,
  LifeBuoy,
  ShoppingBag,
  Handshake,
  HeartHandshake,
  Landmark,
  LayoutGrid,
  Link2,
  Megaphone,
  MessagesSquare,
  Newspaper,
  Package,
  Radar,
  Rocket,
  Scale,
  Search,
  ShieldCheck,
  UserPlus,
  UserRound,
  Wallet,
} from "lucide-react";
import { ReactNode, useMemo, useState } from "react";

import { CATEGORIES, FIT_LABEL, USE_CASES, UseCase } from "@/lib/useCases";
import { cx, Input } from "./ui";

export const CATEGORY_ICON: Record<string, ReactNode> = {
  sales: <Handshake size={16} />,
  marketing: <Megaphone size={16} />,
  research: <MessagesSquare size={16} />,
  product: <Rocket size={16} />,
  fundraising: <Landmark size={16} />,
  hiring: <UserPlus size={16} />,
  partnerships: <Link2 size={16} />,
  success: <HeartHandshake size={16} />,
  finance: <Wallet size={16} />,
  operations: <Package size={16} />,
  pr: <Newspaper size={16} />,
  intel: <Radar size={16} />,
  agency: <Building2 size={16} />,
  founder: <UserRound size={16} />,
  legal: <Scale size={16} />,
  it: <ShieldCheck size={16} />,
  support: <LifeBuoy size={16} />,
  revops: <Gauge size={16} />,
  data: <BarChart3 size={16} />,
  engineering: <Code2 size={16} />,
  ecommerce: <ShoppingBag size={16} />,
};

export function FitBadge({ fit }: { fit: UseCase["fit"] }) {
  const tone = fit === "H" ? "bg-emerald-50 text-emerald-700" : fit === "M" ? "bg-zinc-50 text-zinc-700" : "bg-gray-100 text-gray-600";
  return <span className={cx("shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold", tone)}>{FIT_LABEL[fit]}</span>;
}

export function UseCaseCard({ uc, onPick, cta = "Start this goal" }: { uc: UseCase; onPick: (uc: UseCase) => void; cta?: string }) {
  return (
    <button
      onClick={() => onPick(uc)}
      className="group flex h-full flex-col rounded-xl border border-line bg-white p-4 text-left transition hover:-translate-y-0.5 hover:border-brand-500 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">
          <span className="text-gray-400">{CATEGORY_ICON[uc.categoryKey]}</span>
          {uc.sub}
        </span>
        <FitBadge fit={uc.fit} />
      </div>
      <p className="mt-2 flex-1 text-[14px] font-semibold leading-snug">{uc.goal}</p>
      <p className="mt-2 text-xs text-muted">
        <span className="font-semibold text-gray-600">Counts when:</span> {uc.doneWhen}
      </p>
      <span className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-brand-600 opacity-80 group-hover:opacity-100">
        {cta} <ArrowRight size={13} />
      </span>
    </button>
  );
}

/** Browse everything Autopilot can be hired for. */
export function UseCaseLibrary({ onPick, onCustom }: { onPick: (uc: UseCase) => void; onCustom?: () => void }) {
  const [cat, setCat] = useState<string>("all");
  const [q, setQ] = useState("");
  const [hideLimited, setHideLimited] = useState(true);

  const list = useMemo(() => {
    const term = q.trim().toLowerCase();
    return USE_CASES.filter(
      (u) =>
        (cat === "all" || u.categoryKey === cat) &&
        (!hideLimited || u.fit !== "L") &&
        (!term || `${u.goal} ${u.sub} ${u.category} ${u.doneWhen}`.toLowerCase().includes(term)),
    ).sort((a, b) => "HML".indexOf(a.fit) - "HML".indexOf(b.fit));
  }, [cat, q, hideLimited]);

  const active = CATEGORIES.find((c) => c.key === cat);

  return (
    <div className="grid gap-5 lg:grid-cols-[250px_minmax(0,1fr)]">
      <nav className="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible lg:pb-0">
        <CatButton on={cat === "all"} onClick={() => setCat("all")} icon={<LayoutGrid size={16} />} label="All goals" count={USE_CASES.filter((u) => !hideLimited || u.fit !== "L").length} />
        {CATEGORIES.map((c) => (
          <CatButton key={c.key} on={cat === c.key} onClick={() => setCat(c.key)} icon={CATEGORY_ICON[c.key]} label={c.name}
            count={c.rows.filter((r) => !hideLimited || r[3] !== "L").length} />
        ))}
      </nav>

      <div className="min-w-0">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="relative min-w-56 flex-1">
            <Search size={15} className="absolute left-3 top-2.5 text-muted" />
            <Input className="pl-9" placeholder="Search goals, e.g. meetings, investors, backlinks, reviews" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-muted">
            <input type="checkbox" className="h-4 w-4 accent-brand-500" checked={hideLimited} onChange={(e) => setHideLimited(e.target.checked)} />
            Best fits only
          </label>
        </div>
        {active && <p className="mb-4 text-sm text-muted">{active.blurb}</p>}
        {cat === "all" && !q.trim() ? (
          <div className="space-y-8">
            {onCustom && <CustomCard onCustom={onCustom} />}
            {CATEGORIES.map((c) => {
              const items = list.filter((u) => u.categoryKey === c.key);
              if (!items.length) return null;
              return (
                <section key={c.key}>
                  <div className="mb-2 flex items-end justify-between gap-3">
                    <div>
                      <h3 className="flex items-center gap-2 text-[15px] font-bold"><span className="text-gray-400">{CATEGORY_ICON[c.key]}</span>{c.name}</h3>
                      <p className="text-xs text-muted">{c.blurb}</p>
                    </div>
                    {items.length > 3 && (
                      <button onClick={() => setCat(c.key)} className="shrink-0 text-xs font-semibold text-brand-600 hover:underline">See all {items.length} →</button>
                    )}
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {items.slice(0, 3).map((uc) => <UseCaseCard key={uc.id} uc={uc} onPick={onPick} />)}
                  </div>
                </section>
              );
            })}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {onCustom && <CustomCard onCustom={onCustom} />}
            {list.map((uc) => <UseCaseCard key={uc.id} uc={uc} onPick={onPick} />)}
          </div>
        )}
        {!list.length && <p className="py-10 text-center text-sm text-muted">No goals match. Try another word, or describe your own.</p>}
      </div>
    </div>
  );
}

function CustomCard({ onCustom }: { onCustom: () => void }) {
  return (
    <button onClick={onCustom} className="flex min-h-28 w-full flex-col items-start justify-center rounded-xl border-2 border-dashed border-line bg-white/60 p-4 text-left hover:border-brand-500">
      <span className="text-[14px] font-semibold">Describe your own goal</span>
      <span className="mt-1 text-xs text-muted">Anything with a clear, countable finish line works best.</span>
    </button>
  );
}

function CatButton({ on, onClick, icon, label, count }: { on: boolean; onClick: () => void; icon: ReactNode; label: string; count: number }) {
  return (
    <button
      onClick={onClick}
      className={cx(
        "flex shrink-0 items-center gap-2.5 whitespace-nowrap rounded-lg px-3 py-2 text-left text-[13px] font-semibold transition",
        on ? "bg-white text-brand-700 shadow-sm ring-1 ring-line" : "text-gray-600 hover:bg-white/70 hover:text-ink",
      )}
    >
      <span className={on ? "text-brand-600" : "text-gray-400"}>{icon}</span>
      <span className="flex-1">{label}</span>
      <span className="text-[11px] font-medium text-gray-400">{count}</span>
    </button>
  );
}
