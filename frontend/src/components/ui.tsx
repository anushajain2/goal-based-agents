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
    primary: "bg-brand-500 text-white hover:bg-brand-600 border-transparent",
    secondary: "bg-white text-ink hover:bg-gray-50 border-line",
    ghost: "bg-transparent text-ink hover:bg-black/5 border-transparent",
    danger: "bg-white text-red-700 hover:bg-red-50 border-red-200",
    success: "bg-emerald-600 text-white hover:bg-emerald-700 border-transparent",
  };
  return (
    <button
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-md border font-semibold transition disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-3.5 text-sm",
        styles[variant],
        className,
      )}
    />
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("rounded-lg border border-line bg-white", className)}>{children}</div>;
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b border-line px-4 py-3">
      <div>
        <h3 className="text-[15px] font-semibold">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

const badgeTones = {
  gray: "bg-gray-100 text-gray-700",
  blue: "bg-brand-50 text-brand-700",
  green: "bg-emerald-50 text-emerald-700",
  amber: "bg-amber-50 text-amber-800",
  red: "bg-red-50 text-red-700",
  violet: "bg-violet-50 text-violet-700",
};
export type Tone = keyof typeof badgeTones;

export function Badge({ tone = "gray", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", badgeTones[tone], className)}>
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
      <span className="mb-1 block text-[13px] font-semibold">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

const inputCls =
  "w-full rounded-md border border-line bg-white px-3 py-2 text-sm outline-none transition placeholder:text-gray-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-100";

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
    <div className="flex gap-1 overflow-x-auto border-b border-line px-2">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={cx(
            "-mb-px shrink-0 whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-semibold transition",
            value === t.key ? "border-brand-500 text-brand-600" : "border-transparent text-muted hover:text-ink",
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
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      {icon && <div className="mb-3 text-gray-400">{icon}</div>}
      <p className="font-semibold">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{children}</div>;
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
