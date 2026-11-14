import React, { useState } from "react";
import { Pressable, View } from "react-native";
import { Redirect, router } from "expo-router";
import { useTranslation } from "react-i18next";
import Ionicons from "@expo/vector-icons/Ionicons";
import { api } from "@/api/client";
import { useQuery } from "@/lib/useQuery";
import type { Priorities, RotationRequest, RotationResponse, RotationStrategy } from "@/api/types";
import { CoverCalendar, MetricBar, ScoreRing, cropName, useCrops } from "@/components/domain";
import { BackLink, CropPicker } from "@/components/kit";
import { Button, Card, Chip, ErrorView, IconButton, LabeledSlider, Loading, OriginBanner, RiskBadge, Screen, Section, Txt } from "@/components/ui";
import { space, useTheme } from "@/lib/theme";
import { useStore } from "@/state/store";

const PRIO_KEYS: (keyof Priorities)[] = ["water", "soil", "income", "pests", "risk"];
const MONTHS = (lang: string) =>
  Array.from({ length: 12 }, (_, m) => new Date(Date.UTC(2020, m, 1)).toLocaleDateString(lang, { month: "short", timeZone: "UTC" }));

function Bullets({ items, icon, color }: { items: string[]; icon: React.ComponentProps<typeof Ionicons>["name"]; color: string }) {
  return (
    <View>
      {items.map((s, i) => (
        <View key={i} style={{ flexDirection: "row", gap: space.sm, marginTop: 4 }}>
          <Ionicons name={icon} size={16} color={color} style={{ marginTop: 3 }} />
          <Txt style={{ flex: 1 }}>{s}</Txt>
        </View>
      ))}
    </View>
  );
}

function StrategyCard({ s, idx }: { s: RotationStrategy; idx: number }) {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const { settings } = useStore();
  const crops = useCrops();
  const [open, setOpen] = useState(idx < 2);
  return (
    <Card style={s.is_current ? { borderColor: t.textMuted, borderWidth: 1, borderStyle: "dashed" } : undefined}>
      <View testID={`strategy-${idx}`} style={{ flexDirection: "row", gap: space.md, alignItems: "center" }}>
        <ScoreRing score={s.total_score} label={tr("rotations.score")} />
        <View style={{ flex: 1 }}>
          {s.is_current ? (
            <Txt v="small" color={t.textMuted} style={{ fontWeight: "800" }}>
              {tr("rotations.yourRotation").toUpperCase()}
            </Txt>
          ) : null}
          <Txt v="h3">{s.name}</Txt>
          <Txt v="small" muted>
            {s.slots.map((sl) => cropName(crops, sl.crop)).join(" → ")}
          </Txt>
        </View>
      </View>
      <View style={{ marginTop: space.md }}>
        <CoverCalendar strategy={s} crops={crops} />
      </View>
      <View style={{ marginTop: space.sm }}>
        {s.metrics.map((m) => (
          <MetricBar key={m.id} m={m} system={settings.units} />
        ))}
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityLabel={open ? tr("rotations.hideDetails") : tr("rotations.details")}
        onPress={() => setOpen((o) => !o)}
        style={{ minHeight: 44, flexDirection: "row", alignItems: "center", gap: 6, marginTop: space.sm }}
      >
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={18} color={t.link} />
        <Txt color={t.link} v="label">
          {open ? tr("rotations.hideDetails") : tr("rotations.details")}
        </Txt>
      </Pressable>
      {open ? (
        <View>
          <Txt v="label" style={{ marginTop: space.sm }}>
            {tr("rotations.whySuggested")}
          </Txt>
          <Txt>{s.why_suggested}</Txt>
          {s.evidence.length ? (
            <>
              <Txt v="label" style={{ marginTop: space.md }}>
                {tr("rotations.evidence")}
              </Txt>
              <Bullets items={s.evidence} icon="analytics" color={t.chart[1]} />
            </>
          ) : null}
          {s.benefits.length ? (
            <>
              <Txt v="label" style={{ marginTop: space.md }}>
                {tr("rotations.benefits")}
              </Txt>
              <Bullets items={s.benefits} icon="checkmark-circle" color={t.risk.low.dot} />
            </>
          ) : null}
          {s.info_gaps.length ? (
            <>
              <Txt v="label" style={{ marginTop: space.md }}>
                {tr("rotations.gaps")}
              </Txt>
              <Bullets items={s.info_gaps} icon="help-circle" color={t.textMuted} />
            </>
          ) : null}
          {s.risks_local_review.length ? (
            <>
              <Txt v="label" style={{ marginTop: space.md }}>
                {tr("rotations.risks")}
              </Txt>
              <Bullets items={s.risks_local_review} icon="people" color={t.accent} />
            </>
          ) : null}
        </View>
      ) : null}
    </Card>
  );
}

export default function Rotations() {
  const t = useTheme();
  const { t: tr, i18n } = useTranslation();
  const { field, setField, settings } = useStore();
  const crops = useCrops();
  const [prio, setPrio] = useState<Priorities>({ water: 0.8, soil: 0.6, income: 0.6, pests: 0.4, risk: 0.5 });
  const [editing, setEditing] = useState(false);
  // priorities are committed on "update" so slider drags don't fire a request per tick
  const [committedPrio, setCommittedPrio] = useState<Priorities>(prio);
  const req: RotationRequest | null = field
    ? { lat: field.lat, lon: field.lon, current_rotation: field.current_rotation, irrigation: field.irrigation, priorities: committedPrio, lang: settings.lang }
    : null;
  const q = useQuery<RotationResponse>(req ? JSON.stringify(req) : null, () => api.rotations(req!));
  const { data, origin, savedAt, error, loading } = q;
  const run = () => (JSON.stringify(prio) === JSON.stringify(committedPrio) ? q.refetch() : setCommittedPrio(prio));

  if (!field) return <Redirect href="/onboarding" />;
  const rot = field.current_rotation;
  const setRot = (r: string[]) => setField({ ...field, current_rotation: r });
  const sorted = data ? [...data.strategies].sort((a, b) => (a.is_current ? -1 : b.is_current ? 1 : b.total_score - a.total_score)) : [];
  const months = MONTHS(i18n.language);

  return (
    <Screen testID="rotations">
      <BackLink label={tr("tabs.insights")} onPress={() => router.navigate("/insights")} testID="back-insights" />
      <Txt v="h1">{tr("rotations.title")}</Txt>
      <Txt muted style={{ marginTop: 4 }}>
        {tr("rotations.subtitle")}
      </Txt>
      <OriginBanner origin={origin} savedAt={savedAt} />

      <Section
        title={tr("rotations.current")}
        right={<Chip label={editing ? tr("common.save") : tr("common.change")} icon={editing ? "checkmark" : "create"} onPress={() => setEditing((e) => !e)} />}
      >
        <Card>
          {!editing ? (
            <Txt v="label">{rot.map((c) => cropName(crops, c)).join(" → ")}</Txt>
          ) : (
            <View>
              {rot.map((c, i) => (
                <View key={i} style={{ marginBottom: space.md }}>
                  <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                    <Txt v="label">{tr("rotations.yearN", { n: i + 1 })}</Txt>
                    {rot.length > 1 ? (
                      <IconButton icon="trash" label={tr("rotations.removeYear")} onPress={() => setRot(rot.filter((_, j) => j !== i))} />
                    ) : null}
                  </View>
                  <CropPicker
                    label={tr("rotations.yearN", { n: i + 1 })}
                    value={c}
                    onChange={(id) => id && setRot(rot.map((x, j) => (j === i ? id : x)))}
                    testID={`rot-crop-${i}`}
                  />
                </View>
              ))}
              {rot.length < 6 ? (
                <Button kind="secondary" icon="add" label={tr("rotations.addYear")} onPress={() => setRot([...rot, rot[rot.length - 1]])} />
              ) : null}
            </View>
          )}
        </Card>
      </Section>

      <Section title={tr("rotations.priorities")}>
        <Card>
          {PRIO_KEYS.map((k) => (
            <LabeledSlider
              key={k}
              label={tr(`rotations.prio.${k}`)}
              value={prio[k]}
              min={0}
              max={1}
              step={0.1}
              onChange={(v) => setPrio((p) => ({ ...p, [k]: Math.round(v * 10) / 10 }))}
              format={(v) => "●".repeat(Math.round(v * 5)).padEnd(5, "○")}
              testID={`prio-${k}`}
            />
          ))}
          <Button label={tr("rotations.update")} icon="refresh" onPress={run} disabled={loading} testID="rotations-update" />
        </Card>
      </Section>

      {loading && !data ? <Loading /> : null}
      {error ? <ErrorView message={error} onRetry={run} /> : null}

      {data ? (
        <>
          {data.climate_context.length ? (
            <Section title={tr("rotations.context")}>
              <Card alt>
                <Bullets items={data.climate_context} icon="planet" color={t.primary} />
              </Card>
            </Section>
          ) : null}
          {data.vulnerable_periods.length ? (
            <Section title={tr("rotations.vulnerable")}>
              <Card>
                {data.vulnerable_periods.map((v, i) => (
                  <View key={i} style={{ flexDirection: "row", gap: space.md, alignItems: "center", marginTop: i ? space.sm : 0 }}>
                    <Txt v="label" style={{ width: 44 }}>
                      {months[v.month - 1]}
                    </Txt>
                    <Txt style={{ flex: 1 }}>{v.issue}</Txt>
                    <RiskBadge risk={v.risk} />
                  </View>
                ))}
              </Card>
            </Section>
          ) : null}
          <Section title={tr("rotations.compare")}>
            {sorted.map((s, i) => (
              <StrategyCard key={s.id} s={s} idx={i} />
            ))}
          </Section>
          <Card alt>
            <View style={{ flexDirection: "row", gap: space.sm }}>
              <Ionicons name="people-circle" size={22} color={t.accent} />
              <Txt style={{ flex: 1 }}>{data.disclaimer || tr("rotations.disclaimer")}</Txt>
            </View>
          </Card>
        </>
      ) : null}
    </Screen>
  );
}
