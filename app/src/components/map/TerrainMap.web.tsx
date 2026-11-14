import React, { useEffect, useMemo, useRef, useState } from "react";
import { View } from "react-native";
import { terrainHtml, type TerrainMapProps } from "./terrainHtml";

/** Web terrain map: Leaflet in an iframe (srcDoc). Native uses TerrainMap.tsx (WebView). */
export default function TerrainMap({ lat, lon, polygon, base, overlay, opacity, onOverlayError, fitNonce, height = 380, accessibilityLabel }: TerrainMapProps) {
  const ref = useRef<HTMLIFrameElement | null>(null);
  const [ready, setReady] = useState(false);
  const errRef = useRef(onOverlayError);
  useEffect(() => {
    errRef.current = onOverlayError;
  });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const html = useMemo(() => terrainHtml({ lat, lon }), []);
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.source !== ref.current?.contentWindow) return;
      const d = e.data as { __fieldshift?: boolean; payload?: { type: string } };
      if (!d?.__fieldshift || !d.payload) return;
      if (d.payload.type === "ready") setReady(true);
      if (d.payload.type === "overlayError") errRef.current?.();
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);
  const post = (payload: object) => ref.current?.contentWindow?.postMessage({ __fieldshiftIn: true, payload }, "*");
  useEffect(() => {
    if (ready) post({ type: "field", lat, lon, polygon: polygon ?? [] });
  }, [ready, lat, lon, polygon]);
  useEffect(() => {
    if (ready) post({ type: "base", id: base });
  }, [ready, base]);
  useEffect(() => {
    if (ready) post({ type: "overlay", url: overlay?.url ?? null, bounds: overlay?.bounds, opacity, attribution: overlay?.attribution });
    // opacity changes are sent separately so the overlay is not reloaded
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, overlay?.url]);
  useEffect(() => {
    if (ready) post({ type: "opacity", value: opacity });
  }, [ready, opacity]);
  useEffect(() => {
    if (ready && fitNonce) post({ type: "fit" });
  }, [ready, fitNonce]);
  return (
    <View style={{ height, borderRadius: 16, overflow: "hidden" }} accessibilityLabel={accessibilityLabel}>
      {React.createElement("iframe", {
        ref,
        srcDoc: html,
        title: accessibilityLabel,
        style: { border: 0, width: "100%", height: "100%" },
        "data-testid": "terrain-map-iframe",
      })}
    </View>
  );
}
