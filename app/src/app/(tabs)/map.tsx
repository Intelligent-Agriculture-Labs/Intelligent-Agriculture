import React, { useRef, useState } from "react";
import { Pressable, useWindowDimensions, View } from "react-native";
import { Redirect } from "expo-router";
import { useTranslation } from "react-i18next";
import Ionicons from "@expo/vector-icons/Ionicons";
import { api } from "@/api/client";
import { useQuery } from "@/lib/useQuery";
import type { TerrainLayer, TerrainResponse } from "@/api/types";
import TerrainMap from "@/components/map/TerrainMap";
import type { BaseLayer } from "@/components/map/terrainHtml";
import { Card, Chip, ChipRow, ErrorView, LabeledSlider, Loading, OriginBanner, Screen, Section, Txt } from "@/components/ui";
import { space, useTheme } from "@/lib/theme";
import { fmt } from "@/lib/units";
import { useStore } from "@/state/store";

type LayerId = TerrainLayer["id"];
const OVERLAYS: LayerId[] = ["zones", "erosion", "slope", "wetness", "frost", "elevation"];
const BASES: BaseLayer[] = ["street", "truecolor", "ndvi"];

function Swatch({ color }: { color: string }) {
  const t = useTheme();
  return <View style={{ width: 18, height: 18, borderRadius: 4, backgroundColor: color, borderWidth: 1, borderColor: t.border }} />;
}

export default function MapScreen() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const { width } = useWindowDimensions();
  const { field, settings } = useStore();
  const sys = settings.units;
  const [active, setActive] = useState<LayerId>("zones");
  const [base, setBase] = useState<BaseLayer>("street");
  const [opacity, setOpacity] = useState(0.75);
  const [showSources, setShowSources] = useState(false);
  const retries = useRef(0);
  const q = useQuery<TerrainResponse>(field ? `${field.lat},${field.lon},${field.crop},${JSON.stringify(field.polygon ?? null)}` : null, () =>
    api.terrain({ lat: field!.lat, lon: field!.lon, crop: field!.crop, polygon: field!.polygon && field!.polygon.length >= 3 ? field!.polygon : null }),
  );
  const { data, origin, savedAt, error } = q;
  if (!field) return <Redirect href="/onboarding" />;

  const layer = data?.layers.find((l) => l.id === active) ?? null;
  const overlay =
    data && layer
      ? {
          url: api.abs(layer.png),
          bounds: [
            [data.bounds.south, data.bounds.west],
            [data.bounds.north, data.bounds.east],
          ] as [[number, number], [number, number]],
        }
      : null;
  const onOverlayError = () => {
    // server images expire after restarts: request the maps once more
    if (origin === "live" && retries.current < 1) {
      retries.current += 1;
      q.refetch();
    }
  };
  const statUnit = layer?.unit === "%" ? "%" : layer?.unit === "t/ha/yr" ? "t/ha" : layer?.unit === "m" ? "m" : "";
  const fmtStat = (v: number | undefined) =>
    v === undefined ? "–" : statUnit === "m" ? fmt(v, "m", sys, 0) : `${v.toFixed(statUnit === "t/ha" ? 1 : 2)}${statUnit ? " " + statUnit : ""}`;

  return (
    <Screen testID="map-screen">
      <Txt v="h1">{tr("map.title")}</Txt>
      <Txt muted style={{ marginTop: 4 }}>
        {tr("map.subtitle")}
      </Txt>
      <OriginBanner origin={origin} savedAt={savedAt} />
      {origin === "cache" ? (
        <Txt v="small" muted>
          {tr("map.offlineNote")}
        </Txt>
      ) : null}

      <Section title={tr("map.layers")}>
        <ChipRow>
          {OVERLAYS.map((id) => (
            <Chip key={id} label={tr(`map.layer.${id}`)} selected={active === id} onPress={() => setActive(id)} testID={`layer-${id}`} />
          ))}
        </ChipRow>
      </Section>

      {!data && !error ? <Loading label={tr("map.loading")} /> : null}
      {error && !data ? <ErrorView message={error} onRetry={q.refetch} /> : null}

      {data ? (
        <>
          <View style={{ marginTop: space.md }}>
            <TerrainMap
              lat={field.lat}
              lon={field.lon}
              polygon={field.polygon}
              base={base}
              overlay={overlay}
              opacity={opacity}
              onOverlayError={onOverlayError}
              height={width >= 900 ? 520 : 380}
              accessibilityLabel={tr("map.a11y", { layer: layer ? tr(`map.layer.${layer.id}`) : "" })}
            />
          </View>
          <ChipRow>
            {BASES.map((b) => (
              <Chip
                key={b}
                icon={b === "street" ? "map" : b === "truecolor" ? "earth" : "leaf"}
                label={tr(`map.base.${b}`)}
                selected={base === b}
                onPress={() => setBase(b)}
                testID={`base-${b}`}
              />
            ))}
          </ChipRow>
          <LabeledSlider
            label={tr("map.opacity")}
            value={opacity}
            min={0.2}
            max={1}
            step={0.05}
            onChange={setOpacity}
            format={(v) => `${Math.round(v * 100)} %`}
            testID="opacity"
          />

          {layer ? (
            <Card testID="layer-legend">
              <Txt v="h3">{tr(`map.layer.${layer.id}`)}</Txt>
              <View style={{ marginTop: space.sm, gap: 6 }}>
                {layer.legend.map((li, i) => (
                  <View key={i} style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}>
                    <Swatch color={li.color} />
                    <Txt style={{ flex: 1 }}>{li.label}</Txt>
                    {li.share_pct !== undefined ? (
                      <Txt v="small" muted>
                        {tr("map.ofField", { pct: li.share_pct })}
                      </Txt>
                    ) : null}
                  </View>
                ))}
              </View>
              {layer.stats.mean !== undefined ? (
                <View style={{ flexDirection: "row", gap: space.lg, marginTop: space.md, flexWrap: "wrap" }} testID="layer-stats">
                  <Txt v="small">
                    {tr("map.fieldMean")}:{" "}
                    <Txt v="small" style={{ fontWeight: "700" }}>
                      {fmtStat(layer.stats.mean)}
                    </Txt>
                  </Txt>
                  <Txt v="small">
                    {tr("map.fieldP90")}:{" "}
                    <Txt v="small" style={{ fontWeight: "700" }}>
                      {fmtStat(layer.stats.p90)}
                    </Txt>
                  </Txt>
                </View>
              ) : null}
              <Txt v="small" muted style={{ marginTop: space.md }}>
                {layer.why}
              </Txt>
            </Card>
          ) : null}

          <Section title={tr("map.adviceTitle")}>
            <Txt v="small" muted>
              {tr("map.fieldInfo", {
                area: fmt(data.field.area_ha, "ha", sys, 1),
                texture: data.field.texture,
                rain: fmt(data.field.annual_precip_mm, "mm", sys, 0),
                how: data.field.polygon ? tr("map.byOutline") : tr("map.byRadius"),
              })}
            </Txt>
            {data.zone_advice.map((z) => (
              <Card key={z.id} testID={`zone-${z.id}`}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}>
                  <Swatch color={z.color} />
                  <Txt v="h3" style={{ flex: 1 }}>
                    {z.label}
                  </Txt>
                  <Txt v="label" color={t.primary}>
                    {tr("map.ofField", { pct: z.share_pct })}
                  </Txt>
                </View>
                <Txt style={{ marginTop: space.sm }}>{z.advice}</Txt>
              </Card>
            ))}
          </Section>

          <Pressable
            accessibilityRole="button"
            accessibilityState={{ expanded: showSources }}
            accessibilityLabel={tr("map.sources")}
            onPress={() => setShowSources((v) => !v)}
            style={{ minHeight: 44, flexDirection: "row", alignItems: "center", gap: space.sm, marginTop: space.lg }}
            testID="map-sources-toggle"
          >
            <Ionicons name={showSources ? "chevron-down" : "chevron-forward"} size={18} color={t.link} />
            <Txt color={t.link}>{tr("map.sources")}</Txt>
          </Pressable>
          {showSources ? (
            <Card alt>
              {data.sources.map((s) => (
                <Txt key={s.id} v="small" style={{ marginBottom: 4 }}>
                  • {s.name} — {s.provider} · {s.resolution}
                </Txt>
              ))}
              {data.caveats.map((c, i) => (
                <Txt key={i} v="small" muted style={{ marginTop: 4 }}>
                  ⚠ {c}
                </Txt>
              ))}
            </Card>
          ) : null}
        </>
      ) : null}
    </Screen>
  );
}
