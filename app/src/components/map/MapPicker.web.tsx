import React, { useEffect, useMemo, useRef, useState } from "react";
import { View } from "react-native";
import { leafletHtml, type MapPickerProps } from "./leafletHtml";

export default function MapPicker({ lat, lon, polygon, layer, onPick, height = 300, accessibilityLabel }: MapPickerProps) {
  const ref = useRef<HTMLIFrameElement | null>(null);
  const [ready, setReady] = useState(false);
  const onPickRef = useRef(onPick);
  useEffect(() => {
    onPickRef.current = onPick;
  });
  // build the page once; later state changes are sent as messages so the map keeps its view
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const html = useMemo(() => leafletHtml({ lat: lat ?? 20, lon: lon ?? 0, zoom: lat === null ? 2 : 11 }), []);

  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.source !== ref.current?.contentWindow) return;
      const d = e.data as { __fieldshift?: boolean; payload?: { type: string; lat?: number; lon?: number } };
      if (!d?.__fieldshift || !d.payload) return;
      if (d.payload.type === "ready") setReady(true);
      if (d.payload.type === "click" && d.payload.lat !== undefined && d.payload.lon !== undefined) onPickRef.current(d.payload.lat, d.payload.lon);
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  const post = (payload: object) => ref.current?.contentWindow?.postMessage({ __fieldshiftIn: true, payload }, "*");
  useEffect(() => {
    if (ready && lat !== null && lon !== null) post({ type: "marker", lat, lon, zoom: 12 });
  }, [ready, lat, lon]);
  useEffect(() => {
    if (ready) post({ type: "polygon", points: polygon ?? [] });
  }, [ready, polygon]);
  useEffect(() => {
    if (ready) post({ type: "layer", id: layer });
  }, [ready, layer]);

  return (
    <View style={{ height, borderRadius: 16, overflow: "hidden" }} accessibilityLabel={accessibilityLabel}>
      {React.createElement("iframe", {
        ref,
        srcDoc: html,
        title: accessibilityLabel,
        style: { border: 0, width: "100%", height: "100%" },
        "data-testid": "map-iframe",
      })}
    </View>
  );
}
