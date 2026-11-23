"use client";

import { ButtonHTMLAttributes, ComponentProps, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger" | "success";

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }) {
  const styles: Record<Variant, string> = {
    primary: "bg-brand-500 text-white hover:bg-brand-600 border-transparent shadow-[0_1px_2px_rgb(79_70_229/0.25),inset_0_1px_0_rgb(255_255_255/0.12)]",
    secondary: "bg-white text-ink hover:bg-zinc-50 border-line shadow-[0_1px_2px_rgb(16_24_40/0.05)]",
    ghost: "bg-transparent text-zinc-700 hover:bg-zinc-100 hover:text-ink border-transparent",
    danger: "bg-white text-red-700 hover:bg-red-50 border-red-200",
    success: "bg-emerald-600 text-white hover:bg-emerald-700 border-transparent",
  };
  return (
    <button
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg border font-semibold transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200",
        size === "sm" ? "h-8 px-3 text-[12.5px]" : "h-9 px-4 text-sm",
        styles[variant],
        className,
      )}
    />
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("rounded-2xl border border-line bg-white shadow-[var(--shadow-card)]", className)}>{children}</div>;
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b border-line px-5 py-3.5">
      <div>
        <h3 className="text-[15px] font-semibold">{title}</h3>
        {subtitle && <p className="mt-0.5 text-[12.5px] text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

const badgeTones = {
  gray: "bg-zinc-100 text-zinc-700 ring-zinc-200/60",
  blue: "bg-brand-50 text-brand-700 ring-brand-100",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-100",
  amber: "bg-amber-50 text-amber-800 ring-amber-100",
  red: "bg-red-50 text-red-700 ring-red-100",
  violet: "bg-violet-50 text-violet-700 ring-violet-100",
};
export type Tone = keyof typeof badgeTones;

export function Badge({ tone = "gray", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-semibold ring-1 ring-inset", badgeTones[tone], className)}>
      {children}
    </span>
  );
}

export function Dot({ tone }: { tone: Tone }) {
  const c = { gray: "bg-gray-400", blue: "bg-brand-500", green: "bg-emerald-500", amber: "bg-amber-500", red: "bg-red-500", violet: "bg-violet-500" }[tone];
  return <span className={cx("inline-block h-2 w-2 rounded-full", c)} />;
}

export function Toggle({ on, onChange, disabled, label }: { on: boolean; onChange: (v: boolean) => void; disabled?: boolean; label?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={cx(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition disabled:opacity-40",
        on ? "bg-brand-500" : "bg-gray-300",
      )}
    >
      <span className={cx("inline-block h-4 w-4 rounded-full bg-white shadow transition", on ? "translate-x-4.5" : "translate-x-0.5")} />
    </button>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-semibold text-zinc-800">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

const inputCls =
  "w-full rounded-lg border border-line bg-white px-3 py-2 text-sm shadow-[0_1px_2px_rgb(16_24_40/0.04)] outline-none transition placeholder:text-zinc-400 hover:border-zinc-300 focus:border-brand-500 focus:ring-4 focus:ring-brand-100";

export function Input(props: ComponentProps<"input">) {
  return <input {...props} className={cx(inputCls, props.className)} />;
}
export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx(inputCls, "min-h-20", props.className)} />;
}
export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx(inputCls, "pr-8", props.className)} />;
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { key: T; label: ReactNode }[]; value: T; onChange: (t: T) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-line px-3">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={cx(
            "-mb-px shrink-0 whitespace-nowrap border-b-2 px-3 py-3 text-[13.5px] font-semibold transition",
            value === t.key ? "border-ink text-ink" : "border-transparent text-muted hover:text-ink",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      {icon && <div className="mb-3 grid h-14 w-14 place-items-center rounded-2xl bg-zinc-100 text-zinc-400 [&>svg]:h-7 [&>svg]:w-7">{icon}</div>}
      <p className="font-semibold">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-800">{children}</div>;
}

export const STATUS: Record<string, { label: string; tone: Tone }> = {
  draft: { label: "Draft", tone: "gray" },
  active: { label: "Active", tone: "green" },
  paused: { label: "Paused", tone: "gray" },
  out_of_budget: { label: "Out of budget", tone: "red" },
  completed: { label: "Completed", tone: "blue" },
};

export function CampaignStatus({ status }: { status: string }) {
  const s = STATUS[status] || { label: status, tone: "gray" as Tone };
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px]">
      <Dot tone={s.tone} />
      {s.label}
    </span>
  );
}

/** The top of every page: a title, one short line under it, and the page's main actions. */
export function PageHeader({ title, subtitle, actions, eyebrow }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-[12.5px] font-semibold text-muted">{eyebrow}</div>}
        <h1 className="text-[26px] font-semibold leading-tight tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-[14px] text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** A small section label. */
export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("text-[11.5px] font-semibold uppercase tracking-[0.06em] text-zinc-500", className)}>{children}</div>;
}
