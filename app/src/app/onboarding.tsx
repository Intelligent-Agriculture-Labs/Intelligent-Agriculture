import React, { useEffect, useState } from "react";
import { Pressable, TextInput, View } from "react-native";
import Ionicons from "@expo/vector-icons/Ionicons";
import * as Location from "expo-location";
import { router, useLocalSearchParams } from "expo-router";
import { useTranslation } from "react-i18next";
import { api, ApiError, type Origin } from "@/api/client";
import { openRing, polygonCentroid } from "@/state/farm";
import type { IrrigationMethod, PresetLocation } from "@/api/types";
import MapPicker from "@/components/map/MapPicker";
import type { MapLayer } from "@/components/map/leafletHtml";
import { Button, Chip, ChipRow, DateField, OriginBanner, Screen, Section, Txt, styles as ui } from "@/components/ui";
import { useCrops } from "@/components/domain";
import { space, useTheme } from "@/lib/theme";
import { useStore } from "@/state/store";

const IRRIGATION: IrrigationMethod[] = ["none", "drip", "sprinkler", "pivot", "furrow", "flood"];

function polygonAreaHa(pts: [number, number][]): number {
  // equirectangular approximation, fine for field-sized polygons
  if (pts.length < 3) return 0;
  const lat0 = (pts.reduce((a, p) => a + p[1], 0) / pts.length) * (Math.PI / 180);
  const R = 6371000;
  const xy = pts.map(([lon, lat]) => [((R * (lon * Math.PI)) / 180) * Math.cos(lat0), (R * (lat * Math.PI)) / 180]);
  let s = 0;
  for (let i = 0; i < xy.length; i++) {
    const [x1, y1] = xy[i];
    const [x2, y2] = xy[(i + 1) % xy.length];
    s += x1 * y2 - x2 * y1;
  }
  return Math.abs(s) / 2 / 10000;
}

export default function Onboarding() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const { field, setField } = useStore();
  const crops = useCrops();
  // deep link for demos / scripted captures: fieldshift://onboarding?preset=fallon_nv&replay=1
  const params = useLocalSearchParams<{ preset?: string; replay?: string }>();
  const [presets, setPresets] = useState<PresetLocation[]>([]);
  const [replayDate, setReplayDate] = useState<string | null>(null);
  const [presetOrigin, setPresetOrigin] = useState<Origin | null>(null);
  const [lat, setLat] = useState<number | null>(field?.lat ?? null);
  const [lon, setLon] = useState<number | null>(field?.lon ?? null);
  const [coordText, setCoordText] = useState(field ? `${field.lat}, ${field.lon}` : "");
  const [coordErr, setCoordErr] = useState<string | null>(null);
  const [crop, setCrop] = useState(field?.crop ?? "maize");
  const [date, setDate] = useState(field?.planting_date ?? new Date().toISOString().slice(0, 10));
  const [irrigation, setIrrigation] = useState<IrrigationMethod>(field?.irrigation ?? "none");
  const [presetId, setPresetId] = useState<string | null>(field?.presetId ?? null);
  const [rotation, setRotation] = useState<string[]>(field?.current_rotation ?? []);
  const [name, setName] = useState(field?.name ?? "");
  const [layer, setLayer] = useState<MapLayer>("street");
  const [drawing, setDrawing] = useState(false);
  const [detectOn, setDetectOn] = useState(false);
  const [detectBusy, setDetectBusy] = useState(false);
  const [detectMsg, setDetectMsg] = useState<string | null>(null);
  const [polygon, setPolygon] = useState<[number, number][]>(field?.polygon ?? []);
  const [gpsMsg, setGpsMsg] = useState<string | null>(null);

  useEffect(() => {
    api
      .presets()
      .then((r) => {
        setPresets(r.data);
        setPresetOrigin(r.origin);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const p = params.preset ? presets.find((x) => x.id === params.preset) : undefined;
    if (!p) return;
    setField({
      lat: p.lat,
      lon: p.lon,
      crop: p.crop,
      planting_date: p.planting_date,
      irrigation: p.irrigation,
      name: p.name,
      presetId: p.id,
      current_rotation: p.current_rotation,
      polygon: p.polygon && p.polygon.length >= 3 ? p.polygon : undefined,
      replay_date: p.replay_date ?? null,
      as_of: params.replay === "1" ? (p.replay_date ?? null) : null,
    });
    router.replace("/home");
  }, [params.preset, params.replay, presets, setField]);

  const detect = async (la: number, lo: number) => {
    if (detectBusy) return;
    setDetectBusy(true);
    setDetectMsg(null);
    try {
      const res = await api.detectField({ lat: la, lon: lo, source: "esri" });
      const ring = openRing(res.polygon);
      if (ring.length < 3) throw new Error("empty");
      const c = polygonCentroid(ring);
      setPolygon(ring);
      setLat(+c.lat.toFixed(6));
      setLon(+c.lon.toFixed(6));
      setCoordText(`${c.lat.toFixed(5)}, ${c.lon.toFixed(5)}`);
      setPresetId(null);
      setReplayDate(null);
      setName(tr("fields.defaultName", { n: 1 }));
      setDetectOn(false);
      setDetectMsg(tr("detect.onboardingDone", { area: res.area_ha.toFixed(1), pct: Math.round(res.confidence * 100) }));
    } catch (e) {
      setDetectMsg(e instanceof ApiError && (e.status === 422 || e.status === 503) ? tr("detect.notFound") : tr("detect.failed"));
      setDetectOn(false);
      setDrawing(true);
    } finally {
      setDetectBusy(false);
    }
  };

  const pick = (la: number, lo: number) => {
    if (detectOn) {
      detect(la, lo);
      return;
    }
    if (drawing) {
      setPolygon((p) => [...p, [lo, la]]);
      return;
    }
    setLat(la);
    setLon(lo);
    setCoordText(`${la.toFixed(4)}, ${lo.toFixed(4)}`);
    setPresetId(null);
    setReplayDate(null);
    setName(`${la.toFixed(3)}, ${lo.toFixed(3)}`);
  };

  const choosePreset = (p: PresetLocation) => {
    setPresetId(p.id);
    setLat(p.lat);
    setLon(p.lon);
    setCoordText(`${p.lat}, ${p.lon}`);
    setCrop(p.crop);
    setDate(p.planting_date);
    setIrrigation(p.irrigation);
    setRotation(p.current_rotation);
    setName(p.name);
    setPolygon(p.polygon && p.polygon.length >= 3 ? p.polygon : []);
    setReplayDate(p.replay_date ?? null);
  };

  const useGps = async () => {
    setGpsMsg(null);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") {
        setGpsMsg(tr("onboarding.gpsDenied"));
        return;
      }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      pick(+pos.coords.latitude.toFixed(5), +pos.coords.longitude.toFixed(5));
    } catch {
      setGpsMsg(tr("onboarding.gpsDenied"));
    }
  };

  const applyCoords = () => {
    const m = coordText
      .split(/[,;\s]+/)
      .filter(Boolean)
      .map(Number);
    if (m.length === 2 && Math.abs(m[0]) <= 90 && Math.abs(m[1]) <= 180 && m.every(Number.isFinite)) {
      setCoordErr(null);
      pick(m[0], m[1]);
    } else setCoordErr(tr("onboarding.invalidCoords"));
  };

  const start = () => {
    if (lat === null || lon === null) return;
    setField({
      lat,
      lon,
      crop,
      planting_date: date,
      irrigation,
      polygon: polygon.length >= 3 ? polygon : undefined,
      name: name || `${lat.toFixed(3)}, ${lon.toFixed(3)}`,
      presetId,
      current_rotation: rotation.length ? rotation : [crop, crop, crop, crop],
      replay_date: presetId ? replayDate : null,
      as_of: null,
    });
    router.replace("/home");
  };

  return (
    <Screen testID="onboarding">
      <Txt v="small" color={t.primary} style={{ fontWeight: "800", letterSpacing: 1 }}>
        {tr("app.name").toUpperCase()}
      </Txt>
      <Txt v="h1" style={{ marginTop: 4 }}>
        {tr("onboarding.title")}
      </Txt>
      <Txt muted style={{ marginTop: 4 }}>
        {tr("onboarding.subtitle")}
      </Txt>
      <OriginBanner origin={presetOrigin === "mock" ? "mock" : null} />

      {presets.length ? (
        <Section title={tr("onboarding.presets")}>
          {presets.map((p) => {
            const sel = presetId === p.id;
            return (
              <Pressable
                key={p.id}
                accessibilityRole="button"
                accessibilityState={{ selected: sel }}
                accessibilityLabel={`${p.name}. ${p.story}`}
                onPress={() => choosePreset(p)}
                testID={`preset-${p.id}`}
                style={({ pressed }) => ({
                  flexDirection: "row",
                  alignItems: "center",
                  gap: space.md,
                  minHeight: 56,
                  paddingVertical: space.sm,
                  paddingHorizontal: space.md,
                  marginTop: space.sm,
                  borderRadius: 14,
                  borderWidth: sel ? 2 : 1,
                  borderColor: sel ? t.primary : t.border,
                  backgroundColor: sel ? t.cardAlt : t.card,
                  opacity: pressed ? 0.85 : 1,
                })}
              >
                <Ionicons name={sel ? "checkmark-circle" : "location-outline"} size={24} color={t.primary} />
                <View style={{ flex: 1 }}>
                  <Txt v="label">{p.name}</Txt>
                  <Txt v="small" muted numberOfLines={2}>
                    {p.story}
                  </Txt>
                </View>
              </Pressable>
            );
          })}
        </Section>
      ) : null}

      <Section title={tr("onboarding.layer")}>
        <ChipRow>
          <Chip label={tr("onboarding.layerStreet")} selected={layer === "street"} onPress={() => setLayer("street")} icon="map" />
          <Chip label={tr("onboarding.layerSatellite")} selected={layer === "esri"} onPress={() => setLayer("esri")} icon="planet" />
          <Chip label={tr("onboarding.layerNdvi")} selected={layer === "ndvi"} onPress={() => setLayer("ndvi")} icon="leaf" />
        </ChipRow>
        <View style={{ marginTop: space.md }}>
          <MapPicker lat={lat} lon={lon} polygon={polygon} layer={layer} onPick={pick} accessibilityLabel={tr("a11y.map")} />
        </View>
        <ChipRow>
          <Chip label={tr("onboarding.gps")} icon="locate" onPress={useGps} testID="gps" />
          <Chip
            label={tr("detect.mode")}
            icon="sparkles"
            selected={detectOn}
            onPress={() => {
              setDetectOn((d) => !d);
              setDrawing(false);
              setLayer("esri");
              setDetectMsg(null);
            }}
            testID="onboarding-detect"
          />
          <Chip
            label={drawing ? `${tr("onboarding.drawField")} · ${tr("onboarding.fieldPoints", { count: polygon.length })}` : tr("onboarding.drawField")}
            icon="shapes"
            selected={drawing}
            onPress={() => {
              setDrawing((d) => !d);
              setDetectOn(false);
            }}
          />
          {polygon.length ? <Chip label={tr("onboarding.clearField")} icon="trash" onPress={() => setPolygon([])} /> : null}
        </ChipRow>
        {detectOn || detectBusy || detectMsg ? (
          <Txt v="small" muted style={{ marginTop: space.sm }} testID="onboarding-detect-status">
            {detectBusy ? tr("detect.finding") : detectOn ? tr("detect.hint") : detectMsg}
          </Txt>
        ) : null}
        {drawing ? (
          <Txt v="small" muted style={{ marginTop: space.sm }}>
            {tr("onboarding.drawHint")}
            {polygon.length >= 3 ? ` · ${polygonAreaHa(polygon).toFixed(1)} ha` : ""}
          </Txt>
        ) : null}
        {gpsMsg ? (
          <Txt v="small" color={t.risk.high.fg} style={{ marginTop: space.sm }}>
            {gpsMsg}
          </Txt>
        ) : null}
        <View style={{ flexDirection: "row", gap: space.sm, marginTop: space.md }}>
          <TextInput
            accessibilityLabel={tr("onboarding.searchPlaceholder")}
            placeholder={tr("onboarding.searchPlaceholder")}
            placeholderTextColor={t.textMuted}
            value={coordText}
            onChangeText={setCoordText}
            onSubmitEditing={applyCoords}
            style={[ui.input, { flex: 1, color: t.text, borderColor: t.border, backgroundColor: t.card }]}
            testID="coords"
          />
          <Button kind="secondary" label="OK" onPress={applyCoords} accessibilityLabel={tr("onboarding.searchPlaceholder")} />
        </View>
        {coordErr ? (
          <Txt v="small" color={t.risk.severe.fg}>
            {coordErr}
          </Txt>
        ) : null}
        {lat !== null && lon !== null ? (
          <Txt v="small" muted style={{ marginTop: space.sm }}>
            {tr("onboarding.selected", { lat: lat.toFixed(4), lon: lon.toFixed(4) })}
          </Txt>
        ) : null}
      </Section>

      <Section title={tr("onboarding.crop")}>
        <ChipRow>
          {crops
            .filter((c) => c.type !== "cover")
            .map((c) => (
              <Chip key={c.id} label={c.name} selected={crop === c.id} onPress={() => setCrop(c.id)} testID={`crop-${c.id}`} />
            ))}
        </ChipRow>
      </Section>

      <DateField label={tr("onboarding.plantingDate")} value={date} onChange={setDate} testID="planting-date" />

      <Section title={tr("onboarding.irrigation")}>
        <ChipRow>
          {IRRIGATION.map((m) => (
            <Chip key={m} label={tr(`irrigation.${m}`)} selected={irrigation === m} onPress={() => setIrrigation(m)} />
          ))}
        </ChipRow>
      </Section>

      <Button
        label={tr("onboarding.start")}
        icon="arrow-forward"
        onPress={start}
        disabled={lat === null || lon === null}
        testID="start"
        style={{ marginTop: space.xl }}
      />
    </Screen>
  );
}
