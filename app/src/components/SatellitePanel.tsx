import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pressable, View } from "react-native";
import Ionicons from "@expo/vector-icons/Ionicons";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import type { SatelliteRequest, SatelliteResponse } from "@/api/types";
import TerrainMap from "@/components/map/TerrainMap";
import type { BaseLayer } from "@/components/map/terrainHtml";
import { isUS } from "@/components/map/leafletHtml";
import { NdviChart } from "@/components/satCharts";
import { Button, Card, Chip, ChipRow, ErrorView, KV, LabeledSlider, Section, Txt } from "@/components/ui";
import { space, useTheme } from "@/lib/theme";
import type { Field } from "@/state/farm";

const POLL_MS = 3000;
const MAX_POLLS = 200; // ~10 min

type SatState = { data: SatelliteResponse | null; fromCache: boolean; savedAt: string | null; error: string | null; polling: boolean };

/** Starts (or resumes) the server-side Sentinel-2 job for a field and polls it until done; caches the result per field. */
export function useSatellite(field: Field | null) {
  const req: SatelliteRequest | null = useMemo(
    () => (field ? { lat: field.lat, lon: field.lon, polygon: field.polygon && field.polygon.length >= 3 ? field.polygon : null, crop: field.crop } : null),
    [field],
  );
  const key = req ? api.satelliteKey(req) : null;
  const [state, setState] = useState<SatState>({ data: null, fromCache: false, savedAt: null, error: null, polling: false });
  const [nonce, setNonce] = useState(0);
  const reqRef = useRef(req);
  useEffect(() => {
    reqRef.current = req;
  });

  useEffect(() => {
    if (!key || !reqRef.current) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const r = reqRef.current;
    setState({ data: null, fromCache: false, savedAt: null, error: null, polling: true });
    api.cachedSatellite(key).then((c) => {
      if (alive && c && c.data.status === "done") setState((s) => (s.data && !s.fromCache ? s : { ...s, data: c.data, fromCache: true, savedAt: c.savedAt }));
    });
    let n = 0;
    const tick = async () => {
      n += 1;
      try {
        const res = await api.satelliteOnce(r);
        if (!alive) return;
        if (res.status === "done") {
          await api.saveSatellite(key, res);
          setState({ data: res, fromCache: false, savedAt: new Date().toISOString(), error: null, polling: false });
          return;
        }
        if (res.status === "error") {
          setState((s) => ({ ...s, error: res.message ?? "error", polling: false }));
          return;
        }
        // processing: keep showing cached data (if any) and the progress of the new job
        setState(
          (s) => (s.data && s.fromCache ? { ...s, polling: true, error: null, progressMsg: res } : { ...s, data: res, polling: true, error: null }) as SatState,
        );
        if (n < MAX_POLLS) timer = setTimeout(tick, POLL_MS);
      } catch (e) {
        if (!alive) return;
        setState((s) => ({ ...s, error: e instanceof Error ? e.message : String(e), polling: false }));
      }
    };
    tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [key, nonce]);

  const retry = useCallback(() => setNonce((x) => x + 1), []);
  return { ...state, retry };
}

type Overlay = "zones" | "ndvi" | "truecolor" | "none";

function Swatch({ color }: { color: string }) {
  const t = useTheme();
  return <View style={{ width: 18, height: 18, borderRadius: 4, backgroundColor: color, borderWidth: 1, borderColor: t.border }} />;
}

export function SatellitePanel({ field, expert, mapHeight }: { field: Field; expert: boolean; mapHeight: number }) {
  const t = useTheme();
  const { t: tr, i18n } = useTranslation();
  const sat = useSatellite(field);
  const [overlay, setOverlay] = useState<Overlay>("zones");
  const [base, setBase] = useState<BaseLayer>("esri");
  const [opacity, setOpacity] = useState(0.8);
  const [showSources, setShowSources] = useState(false);
  const [fit, setFit] = useState(1);
  const d = sat.data;
  const done = d?.status === "done";
  const processing = !done && (sat.polling || d?.status === "processing");
  const fmtDate = (iso?: string | null) =>
    iso ? new Date(`${iso}T00:00:00Z`).toLocaleDateString(i18n.language, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "–";

  const bounds = d?.bounds
    ? ([
        [d.bounds.south, d.bounds.west],
        [d.bounds.north, d.bounds.east],
      ] as [[number, number], [number, number]])
    : null;
  const ovUrl =
    !done || !bounds
      ? null
      : overlay === "zones"
        ? d.zones?.png
        : overlay === "ndvi"
          ? d.latest?.ndvi_png
          : overlay === "truecolor"
            ? d.latest?.truecolor_png
            : null;
  const mapOverlay = ovUrl && bounds ? { url: api.abs(ovUrl), bounds, attribution: "Sentinel-2 L2A (ESA Copernicus) via Element 84 Earth Search" } : null;

  return (
    <View testID="satellite-panel">
      {!field.polygon ? (
        <Card alt>
          <Txt v="small">{tr("sat.noOutline")}</Txt>
        </Card>
      ) : null}

      {processing ? (
        <Card testID="sat-progress">
          <Txt v="label">{tr("sat.processing")}</Txt>
          <View style={{ height: 10, borderRadius: 5, backgroundColor: t.cardAlt, marginTop: space.sm, overflow: "hidden" }}>
            <View style={{ width: `${Math.round(100 * Math.min(1, Math.max(0.03, d?.progress ?? 0.03)))}%`, height: 10, backgroundColor: t.primary }} />
          </View>
          <Txt v="small" muted style={{ marginTop: space.xs }}>
            {d?.message ?? tr("sat.processingHint")}
          </Txt>
          {sat.fromCache ? (
            <Txt v="small" muted>
              {tr("sat.showingCached", { date: sat.savedAt ? new Date(sat.savedAt).toLocaleDateString(i18n.language) : "" })}
            </Txt>
          ) : null}
        </Card>
      ) : null}
      {sat.error && !done ? <ErrorView message={sat.error} onRetry={sat.retry} /> : null}
      {sat.error && done ? (
        <Txt v="small" muted>
          {tr("sat.offlineCached", { date: sat.savedAt ? new Date(sat.savedAt).toLocaleDateString(i18n.language) : "" })}
        </Txt>
      ) : null}

      {done && d ? (
        <>
          <View style={{ marginTop: space.md }}>
            <TerrainMap
              lat={field.lat}
              lon={field.lon}
              polygon={field.polygon}
              base={base}
              overlay={mapOverlay}
              opacity={opacity}
              fitNonce={fit}
              height={mapHeight}
              accessibilityLabel={tr("sat.mapA11y", { layer: tr(`sat.overlay.${overlay}`) })}
            />
          </View>
          <ChipRow>
            {(["zones", "ndvi", "truecolor", "none"] as Overlay[]).map((o) => (
              <Chip key={o} label={tr(`sat.overlay.${o}`)} selected={overlay === o} onPress={() => setOverlay(o)} testID={`sat-overlay-${o}`} />
            ))}
            <Chip icon="scan" label={tr("fields.zoomToField")} onPress={() => setFit((n) => n + 1)} />
          </ChipRow>
          <ChipRow>
            {(["esri", ...(isUS(field.lat, field.lon) ? ["naip"] : []), "s2", "street"] as BaseLayer[]).map((b) => (
              <Chip
                key={b}
                icon={b === "esri" ? "image" : b === "naip" ? "flag" : b === "s2" ? "planet" : "map"}
                label={tr(`map.base.${b}`)}
                selected={base === b}
                onPress={() => setBase(b)}
              />
            ))}
          </ChipRow>
          {overlay !== "none" ? (
            <LabeledSlider
              label={tr("map.opacity")}
              value={opacity}
              min={0.2}
              max={1}
              step={0.05}
              onChange={setOpacity}
              format={(v) => `${Math.round(v * 100)} %`}
            />
          ) : null}
          {d.latest ? (
            <Txt v="small" muted>
              {tr("sat.latestScene", { date: fmtDate(d.latest.date) })}
            </Txt>
          ) : null}

          {d.zones ? (
            <Section title={tr("sat.zonesTitle")}>
              <Card testID="sat-zones">
                <Txt v="small" muted>
                  {tr("sat.zonesIntro")}
                </Txt>
                <View style={{ marginTop: space.sm, gap: 6 }}>
                  {d.zones.legend.map((z) => (
                    <View key={z.label} style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}>
                      <Swatch color={z.color} />
                      <Txt style={{ flex: 1 }}>{z.label}</Txt>
                      <Txt v="small" muted>
                        {tr("sat.zoneStats", { pct: z.share_pct, ndvi: z.ndvi_mean.toFixed(2) })}
                      </Txt>
                    </View>
                  ))}
                </View>
                {d.zones.advice.map((a, i) => (
                  <Txt key={i} style={{ marginTop: space.sm }}>
                    • {a}
                  </Txt>
                ))}
                {expert ? (
                  <Txt v="small" muted style={{ marginTop: space.sm }}>
                    {tr("sat.method", { method: d.zones.method, k: d.zones.k, s: d.zones.silhouette !== null ? d.zones.silhouette.toFixed(2) : "–" })}
                  </Txt>
                ) : null}
              </Card>
            </Section>
          ) : null}

          <Section title={tr("sat.seriesTitle")}>
            <Card>
              <NdviChart data={d} />
              {d.phenology ? (
                <View style={{ marginTop: space.sm }} testID="sat-phenology">
                  <KV k={tr("sat.seasonType")} v={d.phenology.season_type} />
                  <KV k={tr("sat.greenup")} v={fmtDate(d.phenology.greenup)} />
                  <KV
                    k={tr("sat.peak")}
                    v={`${fmtDate(d.phenology.peak)}${d.phenology.peak_ndvi !== null ? ` · NDVI ${d.phenology.peak_ndvi.toFixed(2)}` : ""}`}
                  />
                  <KV k={tr("sat.senescence")} v={fmtDate(d.phenology.senescence)} />
                  {d.phenology.bare_periods.length ? (
                    <Txt v="small" muted style={{ marginTop: 4 }}>
                      {tr("sat.bare", {
                        periods: d.phenology.bare_periods.map((b) => `${fmtDate(b.start)} – ${fmtDate(b.end)}`).join("; "),
                      })}
                    </Txt>
                  ) : null}
                </View>
              ) : null}
              <Txt v="small" muted style={{ marginTop: space.sm }}>
                {tr("sat.seriesHint")}
              </Txt>
            </Card>
          </Section>

          {d.kcb_now !== null && d.kcb_now !== undefined ? (
            <Card testID="sat-kcb">
              <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}>
                <Ionicons name="water" size={20} color={t.primary} />
                <Txt v="h3" style={{ flex: 1 }}>
                  {tr("sat.kcbTitle")}
                </Txt>
                <Txt v="h3" color={t.primary}>
                  {d.kcb_now.toFixed(2)}
                </Txt>
              </View>
              <Txt v="small" muted style={{ marginTop: space.sm }}>
                {tr("sat.kcbHint")}
              </Txt>
            </Card>
          ) : null}

          {expert && d.scenes?.length ? (
            <Section title={tr("sat.scenes")}>
              <Card>
                {d.scenes.map((s) => (
                  <Txt key={s.id} v="small" style={{ marginBottom: 2 }}>
                    {s.date} · {tr("sat.sceneRow", { cloud: Math.round(s.cloud_pct), valid: Math.round(s.valid_pct) })} · NDVI{" "}
                    {s.ndvi_mean !== null ? s.ndvi_mean.toFixed(2) : "–"}
                  </Txt>
                ))}
              </Card>
            </Section>
          ) : null}

          <Pressable
            accessibilityRole="button"
            accessibilityState={{ expanded: showSources }}
            accessibilityLabel={tr("map.sources")}
            onPress={() => setShowSources((v) => !v)}
            style={{ minHeight: 44, flexDirection: "row", alignItems: "center", gap: space.sm, marginTop: space.lg }}
          >
            <Ionicons name={showSources ? "chevron-down" : "chevron-forward"} size={18} color={t.link} />
            <Txt color={t.link}>{tr("map.sources")}</Txt>
          </Pressable>
          {showSources ? (
            <Card alt>
              {(d.sources ?? []).map((s) => (
                <Txt key={s.id} v="small" style={{ marginBottom: 4 }}>
                  • {s.name} — {s.provider} · {s.resolution}
                </Txt>
              ))}
              {(d.caveats ?? []).map((c, i) => (
                <Txt key={i} v="small" muted style={{ marginTop: 4 }}>
                  ⚠ {c}
                </Txt>
              ))}
            </Card>
          ) : null}
          <Button kind="ghost" icon="refresh" label={tr("sat.refresh")} onPress={sat.retry} style={{ marginTop: space.sm }} />
        </>
      ) : null}
    </View>
  );
}
