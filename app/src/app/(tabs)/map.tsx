import React, { useRef, useState } from "react";
import { Pressable, useWindowDimensions, View } from "react-native";
import { Redirect, useLocalSearchParams } from "expo-router";
import { useTranslation } from "react-i18next";
import Ionicons from "@expo/vector-icons/Ionicons";
import { api } from "@/api/client";
import { useQuery } from "@/lib/useQuery";
import type { TerrainLayer, TerrainResponse } from "@/api/types";
import TerrainMap from "@/components/map/TerrainMap";
import type { BaseLayer } from "@/components/map/terrainHtml";
import { Card, Chip, ChipRow, ErrorView, LabeledSlider, Loading, OriginBanner, Screen, Section, Txt } from "@/components/ui";
import { Disclosure, InfoButton, Segmented, Sheet } from "@/components/kit";
import type { GlossaryTerm } from "@/components/kit";
import { radius, space, useTheme } from "@/lib/theme";
import { fmt } from "@/lib/units";
import { useStore } from "@/state/store";
import { SatellitePanel } from "@/components/SatellitePanel";
import { isUS } from "@/components/map/leafletHtml";

type LayerId = TerrainLayer["id"];
const OVERLAYS: LayerId[] = ["zones", "erosion", "slope", "wetness", "frost", "elevation"];
const BASES: BaseLayer[] = ["esri", "naip", "s2", "street", "truecolor", "ndvi"];
const BASE_ICON: Record<BaseLayer, "image" | "flag" | "planet" | "map" | "earth" | "leaf"> = {
  esri: "image",
  naip: "flag",
  s2: "planet",
  street: "map",
  truecolor: "earth",
  ndvi: "leaf",
};

const LAYER_TERM: Partial<Record<LayerId, GlossaryTerm>> = { zones: "zones", erosion: "erosion", wetness: "wetness", frost: "frostHollow" };

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
  const [base, setBase] = useState<BaseLayer>("esri");
  const params = useLocalSearchParams<{ view?: string }>();
  // the URL parameter (?view=satellite) decides until the user toggles the segmented control
  const [viewChoice, setView] = useState<"terrain" | "satellite" | null>(null);
  const view: "terrain" | "satellite" = viewChoice ?? (params.view === "satellite" ? "satellite" : "terrain");
  const [opacity, setOpacity] = useState(0.75);
  const [layersOpen, setLayersOpen] = useState(false);
  const retries = useRef(0);
  const q = useQuery<TerrainResponse>(
    field && view === "terrain" ? `${field.lat},${field.lon},${field.crop},${JSON.stringify(field.polygon ?? null)},${settings.lang}` : null,
    () =>
      api.terrain({
        lat: field!.lat,
        lon: field!.lon,
        crop: field!.crop,
        polygon: field!.polygon && field!.polygon.length >= 3 ? field!.polygon : null,
        lang: settings.lang,
      }),
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
        {tr(view === "satellite" ? "map.subtitleSatellite" : "map.subtitle")}
      </Txt>
      <Segmented
        style={{ marginTop: space.md }}
        value={view}
        onChange={setView}
        options={(["terrain", "satellite"] as const).map((v) => ({ value: v, label: tr(`map.view.${v}`), testID: `map-view-${v}` }))}
      />

      {view === "satellite" ? <SatellitePanel field={field} expert={settings.expert} mapHeight={width >= 900 ? 520 : 380} /> : null}
      {view === "terrain" ? (
        <>
          <OriginBanner origin={origin} savedAt={savedAt} />
          {origin === "cache" ? (
            <Txt v="small" muted>
              {tr("map.offlineNote")}
            </Txt>
          ) : null}

          {!data && !error ? <Loading label={tr("map.loading")} /> : null}
          {error && !data ? <ErrorView message={error} onRetry={q.refetch} /> : null}

          {data ? (
            <>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`${tr("map.layersButton")}: ${layer ? tr(`map.layer.${layer.id}`) : ""}`}
                onPress={() => setLayersOpen(true)}
                testID="layers-button"
                style={{
                  flexDirection: "row",
                  alignItems: "center",
                  gap: space.sm,
                  marginTop: space.lg,
                  minHeight: 44,
                  paddingHorizontal: space.md,
                  borderRadius: radius.md,
                  backgroundColor: t.cardAlt,
                }}
              >
                <Ionicons name="layers-outline" size={20} color={t.primary} />
                <Txt v="label" style={{ flex: 1 }}>
                  {layer ? tr(`map.layer.${layer.id}`) : tr("map.layersButton")}
                </Txt>
                <Txt v="small" muted>
                  {tr("map.layersButton")}
                </Txt>
                <Ionicons name="chevron-down" size={16} color={t.textMuted} />
              </Pressable>
              <View style={{ marginTop: space.sm }}>
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
              {layer ? (
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space.md, marginTop: space.sm }} testID="layer-legend-compact">
                  {layer.legend.map((li, i) => (
                    <View key={i} style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                      <Swatch color={li.color} />
                      <Txt v="small">{li.label}</Txt>
                    </View>
                  ))}
                </View>
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

              {layer ? (
                <Disclosure title={tr("map.legendTitle")} subtitle={tr(`map.layer.${layer.id}`)} icon="color-palette-outline" testID="map-legend">
                  <View testID="layer-legend">
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                      <Txt v="h3" style={{ flex: 1 }}>
                        {tr(`map.layer.${layer.id}`)}
                      </Txt>
                      {LAYER_TERM[layer.id] ? <InfoButton term={LAYER_TERM[layer.id]!} /> : null}
                    </View>
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
                  </View>
                </Disclosure>
              ) : null}
              <Disclosure title={tr("map.sources")} icon="document-text-outline" testID="map-sources">
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
              </Disclosure>
            </>
          ) : null}
        </>
      ) : null}
      <Sheet visible={layersOpen} onClose={() => setLayersOpen(false)} title={tr("map.layersButton")} testID="layers-sheet">
        <Txt v="label">{tr("map.layers")}</Txt>
        <ChipRow>
          {OVERLAYS.map((id) => (
            <Chip key={id} label={tr(`map.layer.${id}`)} selected={active === id} onPress={() => setActive(id)} testID={`layer-${id}`} />
          ))}
        </ChipRow>
        <Txt v="label" style={{ marginTop: space.lg }}>
          {tr("map.baseTitle")}
        </Txt>
        <ChipRow>
          {BASES.filter((b) => b !== "naip" || isUS(field.lat, field.lon)).map((b) => (
            <Chip key={b} icon={BASE_ICON[b]} label={tr(`map.base.${b}`)} selected={base === b} onPress={() => setBase(b)} testID={`base-${b}`} />
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
      </Sheet>
    </Screen>
  );
}
