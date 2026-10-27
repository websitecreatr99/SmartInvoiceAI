"use client";

import { motion } from "framer-motion";
import {
  Building2, Calendar, ClipboardList, Hash, Mail, MapPin, Package, Phone, StickyNote, Truck, User,
} from "lucide-react";
import type { Address, Contact, Extraction, Header, LineItem } from "@/lib/types";

const fadeUp = {
  hidden: { opacity: 0, y: 14 },
  show: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.05, duration: 0.4 } }),
};

const KEY_FIELDS: { key: keyof Header; label: string; icon: typeof Hash }[] = [
  { key: "job_name", label: "Job name", icon: ClipboardList },
  { key: "job_number", label: "Job #", icon: Hash },
  { key: "purchase_order_number", label: "PO #", icon: Hash },
  { key: "project_number", label: "Project #", icon: Hash },
  { key: "quote_number", label: "Quote #", icon: Hash },
  { key: "date_ordered", label: "Ordered", icon: Calendar },
  { key: "delivery_date", label: "Delivery", icon: Calendar },
  { key: "ship_via", label: "Ship via", icon: Truck },
  { key: "payment_terms", label: "Payment terms", icon: ClipboardList },
];

/** Share of leaf fields the model managed to fill — a quick read on extraction coverage. */
function coverage(value: unknown): [number, number] {
  if (value === null || value === undefined) return [0, 1];
  if (typeof value !== "object") return [1, 1];
  const children = Array.isArray(value) ? value : Object.values(value);
  return children.reduce<[number, number]>(
    (acc, v) => {
      const [f, t] = coverage(v);
      return [acc[0] + f, acc[1] + t];
    },
    [0, 0],
  );
}

function formatAddress(a: Address) {
  const cityLine = [a.city, a.state, a.zip].filter(Boolean).join(", ");
  return [a.address1, a.address2, a.address3, cityLine, a.country].filter(Boolean);
}

function Dash() {
  return <span className="text-white/25">—</span>;
}

function AddressCard({ title, address, accent }: { title: string; address: Address | null; accent: string }) {
  const lines = address ? formatAddress(address) : [];
  const empty = !address?.name && !lines.length;
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className={`grid h-7 w-7 place-items-center rounded-lg ${accent}`}>
          {title === "Vendor" ? <Building2 className="h-3.5 w-3.5" /> : <MapPin className="h-3.5 w-3.5" />}
        </span>
        <span className="text-xs font-semibold uppercase tracking-wider text-white/50">{title}</span>
      </div>
      {empty ? (
        <p className="text-sm text-white/30 italic">Not found in document</p>
      ) : (
        <>
          <p className="font-semibold">{address?.name ?? <Dash />}</p>
          {lines.map((l, i) => (
            <p key={i} className="text-sm text-white/60">{l}</p>
          ))}
        </>
      )}
    </div>
  );
}

function ContactCard({ title, contact }: { title: string; contact: Contact | null }) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-gradient-to-br from-violet-500/40 to-cyan-500/40 text-sm font-bold">
        {contact?.name?.[0]?.toUpperCase() ?? <User className="h-4 w-4" />}
      </span>
      <div className="min-w-0 space-y-0.5">
        <p className="text-xs font-semibold uppercase tracking-wider text-white/50">{title}</p>
        <p className="font-semibold">{contact?.name ?? <Dash />}</p>
        {contact?.email && (
          <p className="flex items-center gap-1.5 truncate text-sm text-cyan-300"><Mail className="h-3.5 w-3.5 shrink-0" />{contact.email}</p>
        )}
        {contact?.contact_number && (
          <p className="flex items-center gap-1.5 text-sm text-white/60"><Phone className="h-3.5 w-3.5 shrink-0" />{contact.contact_number}</p>
        )}
      </div>
    </div>
  );
}

function LineItemsTable({ items }: { items: LineItem[] }) {
  if (!items.length) return <p className="text-sm text-white/40 italic">No line items detected.</p>;
  return (
    <div className="scroll-thin overflow-x-auto rounded-2xl border border-white/10">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="bg-white/[0.04] text-xs uppercase tracking-wider text-white/45">
          <tr>
            <th className="px-4 py-3 font-semibold">#</th>
            <th className="px-4 py-3 font-semibold">Description</th>
            <th className="px-4 py-3 font-semibold">Part #</th>
            <th className="px-4 py-3 text-right font-semibold">Qty</th>
            <th className="px-4 py-3 font-semibold">UOM</th>
            <th className="px-4 py-3 text-right font-semibold">Unit price</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {items.map((it, i) => {
            const corrected = it.spell_corrected_product_description;
            return (
              <tr key={i} className="transition-colors hover:bg-violet-500/[0.06]">
                <td className="px-4 py-3 font-mono text-white/40">{it.line_no ?? i + 1}</td>
                <td className="px-4 py-3">
                  <p className="font-medium">{corrected ?? it.product_description ?? <Dash />}</p>
                  {corrected && it.product_description && corrected !== it.product_description && (
                    <p className="text-xs text-white/35 line-through decoration-white/20">{it.product_description}</p>
                  )}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-white/60">{it.part_numbers ?? <Dash />}</td>
                <td className="px-4 py-3 text-right font-mono">{it.quantity ?? <Dash />}</td>
                <td className="px-4 py-3 text-white/60">{it.uom ?? <Dash />}</td>
                <td className="px-4 py-3 text-right font-mono">
                  {it.unit_price ? `${it.currency ?? ""} ${it.unit_price}`.trim() : <Dash />}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function DocumentView({ data }: { data: Extraction }) {
  const [filled, total] = coverage(data);
  const pct = total ? Math.round((filled / total) * 100) : 0;
  const lineCount = data.extraction.reduce((n, e) => n + (e.line_items?.length ?? 0), 0);

  return (
    <div className="space-y-8">
      {/* Summary stats */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" custom={0} className="grid grid-cols-3 gap-3">
        {[
          { label: "Orders", value: data.extraction.length },
          { label: "Line items", value: lineCount },
          { label: "Field coverage", value: `${pct}%`, bar: pct },
        ].map((s) => (
          <div key={s.label} className="rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.06] to-transparent p-4">
            <p className="text-xs font-medium text-white/45">{s.label}</p>
            <p className="mt-1 text-2xl font-bold tracking-tight">{s.value}</p>
            {s.bar !== undefined && (
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                <motion.div
                  className="h-full rounded-full bg-gradient-to-r from-violet-400 to-cyan-300"
                  initial={{ width: 0 }}
                  animate={{ width: `${s.bar}%` }}
                  transition={{ duration: 1, ease: "easeOut" }}
                />
              </div>
            )}
          </div>
        ))}
      </motion.div>

      {data.extraction.map((order, oi) => {
        const h = order.header;
        return (
          <div key={oi} className="space-y-6">
            {data.extraction.length > 1 && (
              <div className="flex items-center gap-3">
                <span className="text-sm font-semibold text-violet-300">Order {oi + 1}</span>
                <span className="h-px flex-1 bg-gradient-to-r from-violet-400/40 to-transparent" />
              </div>
            )}

            {h && (
              <>
                <motion.div variants={fadeUp} initial="hidden" animate="show" custom={1} className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {KEY_FIELDS.map(({ key, label, icon: Icon }) => {
                    const v = h[key] as string | null;
                    return (
                      <div key={key} className={`rounded-xl border p-3 ${v ? "border-white/10 bg-white/[0.03]" : "border-white/5 bg-transparent"}`}>
                        <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-white/40">
                          <Icon className="h-3 w-3" />{label}
                        </p>
                        <p className={`mt-1 truncate text-sm font-medium ${v ? "text-white" : "text-white/25"}`}>{v ?? "—"}</p>
                      </div>
                    );
                  })}
                </motion.div>

                <motion.div variants={fadeUp} initial="hidden" animate="show" custom={2} className="grid gap-3 md:grid-cols-3">
                  <AddressCard title="Ship to" address={h.ship_to} accent="bg-cyan-500/15 text-cyan-300" />
                  <AddressCard title="Bill to" address={h.bill_to} accent="bg-violet-500/15 text-violet-300" />
                  <AddressCard title="Vendor" address={h.vendor} accent="bg-fuchsia-500/15 text-fuchsia-300" />
                </motion.div>

                <motion.div variants={fadeUp} initial="hidden" animate="show" custom={3} className="grid gap-3 md:grid-cols-2">
                  <ContactCard title="Buyer contact" contact={h.buyer_contact} />
                  <ContactCard title="Shipping contact" contact={h.shipping_contact} />
                </motion.div>

                {(h.shipping_instructions || h.notes) && (
                  <motion.div variants={fadeUp} initial="hidden" animate="show" custom={4} className="grid gap-3 md:grid-cols-2">
                    {[
                      { label: "Shipping instructions", value: h.shipping_instructions, icon: Truck },
                      { label: "Notes", value: h.notes, icon: StickyNote },
                    ].filter((n) => n.value).map(({ label, value, icon: Icon }) => (
                      <div key={label} className="rounded-2xl border border-amber-300/15 bg-amber-300/[0.04] p-4">
                        <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-amber-200/70">
                          <Icon className="h-3.5 w-3.5" />{label}
                        </p>
                        <p className="whitespace-pre-line text-sm text-white/75">{value}</p>
                      </div>
                    ))}
                  </motion.div>
                )}
              </>
            )}

            <motion.div variants={fadeUp} initial="hidden" animate="show" custom={5}>
              <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <Package className="h-4 w-4 text-violet-300" /> Line items
                <span className="rounded-full bg-white/10 px-2 py-0.5 text-xs text-white/60">{order.line_items?.length ?? 0}</span>
              </h4>
              <LineItemsTable items={order.line_items ?? []} />
            </motion.div>
          </div>
        );
      })}
    </div>
  );
}
