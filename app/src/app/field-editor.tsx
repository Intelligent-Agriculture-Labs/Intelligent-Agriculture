import React, { useMemo, useState } from "react";
import { TextInput, View } from "react-native";
import * as Location from "expo-location";
import { router, Stack, useLocalSearchParams } from "expo-router";
import { useTranslation } from "react-i18next";
import type { IrrigationMethod } from "@/api/types";
import MapPicker from "@/components/map/MapPicker";
import { isUS, type MapLayer } from "@/components/map/leafletHtml";
import { useCrops } from "@/components/domain";
import { Button, Chip, ChipRow, DateField, Screen, Section, Txt, styles as ui } from "@/components/ui";
import { space, useTheme } from "@/lib/theme";
import { fmt, inToMm, mmToIn } from "@/lib/units";
import { polygonAreaHa, polygonCentroid } from "@/state/farm";
import { useStore } from "@/state/store";

const IRRIGATION: IrrigationMethod[] = ["none", "drip", "sprinkler", "pivot", "furrow", "flood"];
const LAYERS: { id: MapLayer; icon: "planet" | "map" | "earth" | "leaf" | "image" | "flag" }[] = [
  { id: "esri", icon: "image" },
  { id: "naip", icon: "flag" },
  { id: "s2", icon: "planet" },
  { id: "street", icon: "map" },
  { id: "truecolor", icon: "earth" },
  { id: "ndvi", icon: "leaf" },
];

/** Add or edit a field: draw its outline on 10 m Sentinel-2 imagery, then set crop, sowing date and irrigation. */
export default function FieldEditor() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const params = useLocalSearchParams<{ id?: string; mode?: string }>();
  const { fields, field: active, addField, updateField, setActiveField, settings } = useStore();
  const crops = useCrops();
  const editing = params.mode === "new" ? null : (fields.find((f) => f.id === params.id) ?? (params.id ? null : active));
  const seed = editing ?? active; // a new field starts where the farm is, so neighbouring fields are visible
  const sys = settings.units;

  const [name, setName] = useState(editing?.name ?? tr("fields.defaultName", { n: fields.length + 1 }));
  const [polygon, setPolygon] = useState<[number, number][]>(editing?.polygon ?? []);
  const [pin, setPin] = useState<{ lat: number; lon: number } | null>(editing ? { lat: editing.lat, lon: editing.lon } : null);
  const [crop, setCrop] = useState(editing?.crop ?? seed?.crop ?? "maize");
  const [date, setDate] = useState(editing?.planting_date ?? seed?.planting_date ?? new Date().toISOString().slice(0, 10));
  const [irrigation, setIrrigation] = useState<IrrigationMethod>(editing?.irrigation ?? seed?.irrigation ?? "none");
  const [alloc, setAlloc] = useState(
    editing?.water_allocation_mm
      ? String(Math.round(sys === "imperial" ? mmToIn(editing.water_allocation_mm) * 10 : editing.water_allocation_mm) / (sys === "imperial" ? 10 : 1))
      : "",
  );
  const [layer, setLayer] = useState<MapLayer>("esri");
  const [mode, setMode] = useState<"draw" | "pin">("draw");
  const [fitNonce, setFitNonce] = useState(0);
  const [coordText, setCoordText] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const area = polygonAreaHa(polygon);
  const center = useMemo(() => (polygon.length >= 3 ? polygonCentroid(polygon) : pin), [polygon, pin]);
  // the map is centred once (on the field, or on the farm for a new field) and then only moves for GPS / typed coordinates,
  // so adding corners does not make the view jump
  const [initialCenter] = useState(() => (editing ? { lat: editing.lat, lon: editing.lon } : seed ? { lat: seed.lat, lon: seed.lon } : null));
  const mapCenter = pin && (!editing || pin.lat !== editing.lat || pin.lon !== editing.lon) ? pin : initialCenter;

  const onPick = (lat: number, lon: number) => {
    if (mode === "draw") setPolygon((p) => [...p, [lon, lat]]);
    else setPin({ lat, lon });
  };
  const onVertexMove = (i: number, lat: number, lon: number) => setPolygon((p) => p.map((q, k) => (k === i ? [lon, lat] : q)));

  const useGps = async () => {
    setMsg(null);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") return setMsg(tr("onboarding.gpsDenied"));
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      setPin({ lat: +pos.coords.latitude.toFixed(6), lon: +pos.coords.longitude.toFixed(6) });
      setMode("draw");
    } catch {
      setMsg(tr("onboarding.gpsDenied"));
    }
  };
  const applyCoords = () => {
    const m = coordText
      .split(/[,;\s]+/)
      .filter(Boolean)
      .map(Number);
    if (m.length === 2 && Math.abs(m[0]) <= 90 && Math.abs(m[1]) <= 180 && m.every(Number.isFinite)) {
      setPin({ lat: m[0], lon: m[1] });
      setMsg(null);
    } else setMsg(tr("onboarding.invalidCoords"));
  };

  const allocMm = (() => {
    const v = parseFloat(alloc.replace(",", "."));
    if (!Number.isFinite(v) || v <= 0) return null;
    return Math.round(sys === "imperial" ? inToMm(v) : v);
  })();
  const canSave = !!center && name.trim().length > 0 && (polygon.length === 0 || polygon.length >= 3);

  const save = () => {
    if (!center) return;
    const draft = {
      name: name.trim(),
      lat: +center.lat.toFixed(6),
      lon: +center.lon.toFixed(6),
      polygon: polygon.length >= 3 ? polygon : undefined,
      crop,
      planting_date: date,
      irrigation,
      water_allocation_mm: irrigation === "none" ? null : allocMm,
    };
    if (editing) {
      const moved = Math.abs(editing.lat - draft.lat) > 0.01 || Math.abs(editing.lon - draft.lon) > 0.01;
      updateField(editing.id, {
        ...draft,
        current_rotation: editing.crop === crop ? editing.current_rotation : [crop, crop, crop, crop],
        // a demo farm moved elsewhere is no longer the demo farm
        presetId: moved ? null : editing.presetId,
        replay_date: moved ? null : editing.replay_date,
        as_of: moved ? null : editing.as_of,
      });
      setActiveField(editing.id);
    } else {
      addField({ ...draft, current_rotation: [crop, crop, crop, crop], presetId: null, replay_date: null, as_of: null });
    }
    if (router.canGoBack()) router.back();
    else router.replace("/home");
  };

  return (
    <Screen testID="field-editor">
      <Stack.Screen options={{ title: editing ? tr("fields.editTitle") : tr("fields.newTitle"), headerShown: false }} />
      <Button
        kind="ghost"
        icon="arrow-back"
        label={tr("common.back")}
        onPress={() => (router.canGoBack() ? router.back() : router.replace("/home"))}
        style={{ alignSelf: "flex-start" }}
        testID="editor-back"
      />
      <Txt v="h1">{editing ? tr("fields.editTitle") : tr("fields.newTitle")}</Txt>
      <Txt muted style={{ marginTop: 4 }}>
        {tr("fields.editorHint")}
      </Txt>

      <Section title={tr("fields.name")}>
        <TextInput
          accessibilityLabel={tr("fields.name")}
          value={name}
          onChangeText={setName}
          style={[ui.input, { color: t.text, borderColor: t.border, backgroundColor: t.card }]}
          testID="field-name"
        />
      </Section>

      <Section title={tr("fields.outline")}>
        <ChipRow>
          {LAYERS.filter((l) => l.id !== "naip" || isUS(mapCenter?.lat, mapCenter?.lon)).map((l) => (
            <Chip
              key={l.id}
              icon={l.icon}
              label={tr(`fields.layer.${l.id}`)}
              selected={layer === l.id}
              onPress={() => setLayer(l.id)}
              testID={`editor-layer-${l.id}`}
            />
          ))}
        </ChipRow>
        <View style={{ marginTop: space.md }}>
          <MapPicker
            lat={mapCenter?.lat ?? null}
            lon={mapCenter?.lon ?? null}
            zoom={17}
            polygon={polygon}
            editable={mode === "draw"}
            layer={layer}
            onPick={onPick}
            onVertexMove={onVertexMove}
            fitNonce={fitNonce}
            height={420}
            accessibilityLabel={tr("fields.mapA11y")}
          />
        </View>
        <ChipRow>
          <Chip icon="shapes" label={tr("fields.modeDraw")} selected={mode === "draw"} onPress={() => setMode("draw")} testID="mode-draw" />
          <Chip icon="pin" label={tr("fields.modePin")} selected={mode === "pin"} onPress={() => setMode("pin")} testID="mode-pin" />
          <Chip icon="arrow-undo" label={tr("fields.undo")} onPress={() => setPolygon((p) => p.slice(0, -1))} testID="undo-point" />
          {polygon.length ? <Chip icon="trash" label={tr("onboarding.clearField")} onPress={() => setPolygon([])} /> : null}
          {polygon.length >= 3 ? <Chip icon="scan" label={tr("fields.zoomToField")} onPress={() => setFitNonce((n) => n + 1)} /> : null}
          <Chip icon="locate" label={tr("onboarding.gps")} onPress={useGps} />
        </ChipRow>
        <Txt v="small" muted style={{ marginTop: space.sm }} testID="field-area">
          {mode === "draw"
            ? polygon.length >= 3
              ? tr("fields.areaLive", { area: fmt(area, "ha", sys, 2), count: polygon.length })
              : tr("fields.drawHint", { count: polygon.length })
            : tr("fields.pinHint")}
        </Txt>
        <View style={{ flexDirection: "row", gap: space.sm, marginTop: space.md }}>
          <TextInput
            accessibilityLabel={tr("onboarding.searchPlaceholder")}
            placeholder={tr("onboarding.searchPlaceholder")}
            placeholderTextColor={t.textMuted}
            value={coordText}
            onChangeText={setCoordText}
            onSubmitEditing={applyCoords}
            style={[ui.input, { flex: 1, color: t.text, borderColor: t.border, backgroundColor: t.card }]}
          />
          <Button kind="secondary" label="OK" onPress={applyCoords} accessibilityLabel={tr("onboarding.searchPlaceholder")} />
        </View>
        {msg ? (
          <Txt v="small" color={t.risk.severe.fg}>
            {msg}
          </Txt>
        ) : null}
      </Section>

      <Section title={tr("onboarding.crop")}>
        <ChipRow>
          {crops
            .filter((c) => c.type !== "cover")
            .map((c) => (
              <Chip key={c.id} label={c.name} selected={crop === c.id} onPress={() => setCrop(c.id)} testID={`editor-crop-${c.id}`} />
            ))}
        </ChipRow>
      </Section>

      <DateField label={tr("onboarding.plantingDate")} value={date} onChange={setDate} />

      <Section title={tr("onboarding.irrigation")}>
        <ChipRow>
          {IRRIGATION.map((m) => (
            <Chip key={m} label={tr(`irrigation.${m}`)} selected={irrigation === m} onPress={() => setIrrigation(m)} />
          ))}
        </ChipRow>
        {irrigation !== "none" ? (
          <View style={{ marginTop: space.md }}>
            <Txt v="label">{tr("fields.allocation", { unit: sys === "imperial" ? "in" : "mm" })}</Txt>
            <TextInput
              accessibilityLabel={tr("fields.allocation", { unit: sys === "imperial" ? "in" : "mm" })}
              keyboardType="decimal-pad"
              value={alloc}
              onChangeText={setAlloc}
              placeholder={tr("fields.allocationPlaceholder")}
              placeholderTextColor={t.textMuted}
              style={[ui.input, { color: t.text, borderColor: t.border, backgroundColor: t.card, marginTop: space.xs }]}
            />
          </View>
        ) : null}
      </Section>

      <Button label={tr("fields.save")} icon="checkmark" onPress={save} disabled={!canSave} testID="field-save" style={{ marginTop: space.xl }} />
      {!center ? (
        <Txt v="small" muted style={{ marginTop: space.sm }}>
          {tr("fields.needLocation")}
        </Txt>
      ) : null}
    </Screen>
  );
}
