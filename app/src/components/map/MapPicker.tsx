import React, { useEffect, useMemo, useRef, useState } from "react";
import { View } from "react-native";
import { WebView as RNWebView, type WebViewMessageEvent } from "react-native-webview";
import { leafletHtml, type MapPickerProps } from "./leafletHtml";

// react-native-webview 14's union prop types collapse to `never` against RN 0.88 typings; narrow to what we use.
type WebViewHandle = { injectJavaScript: (js: string) => void };
const WebView = RNWebView as unknown as React.ComponentType<{
  ref?: React.Ref<WebViewHandle>;
  originWhitelist: string[];
  source: { html: string; baseUrl?: string };
  onMessage: (e: WebViewMessageEvent) => void;
  javaScriptEnabled?: boolean;
  nestedScrollEnabled?: boolean;
  style?: object;
}>;

/** Native (iOS/Android) map: Leaflet inside a WebView. The web build uses MapPicker.web.tsx. */
export default function MapPicker({
  lat,
  lon,
  polygon,
  editable,
  selectedVertex,
  layer,
  onPick,
  onVertexMove,
  onVertexSelect,
  onVertexDelete,
  onInsertVertex,
  fitNonce,
  zoom = 11,
  height = 300,
  accessibilityLabel,
}: MapPickerProps) {
  const ref = useRef<WebViewHandle>(null);
  const [ready, setReady] = useState(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const html = useMemo(() => leafletHtml({ lat: lat ?? 20, lon: lon ?? 0, zoom: lat === null ? 2 : zoom }), []);
  const post = (payload: object) => ref.current?.injectJavaScript(`window.__fieldshiftHandle(${JSON.stringify(payload)});true;`);

  useEffect(() => {
    if (ready && lat !== null && lon !== null) post({ type: "marker", lat, lon, zoom: Math.max(12, zoom) });
  }, [ready, lat, lon, zoom]);
  useEffect(() => {
    if (ready) post({ type: "polygon", points: polygon ?? [], editable: !!editable, selected: selectedVertex ?? null });
  }, [ready, polygon, editable, selectedVertex]);
  useEffect(() => {
    if (ready && fitNonce) post({ type: "fit" });
  }, [ready, fitNonce]);
  useEffect(() => {
    if (ready) post({ type: "layer", id: layer });
  }, [ready, layer]);

  const onMessage = (e: WebViewMessageEvent) => {
    try {
      const m = JSON.parse(e.nativeEvent.data) as { type: string; lat?: number; lon?: number; index?: number; after?: number };
      if (m.type === "ready") setReady(true);
      if (m.type === "click" && m.lat !== undefined && m.lon !== undefined) onPick(m.lat, m.lon);
      if (m.type === "vertexMove" && m.index !== undefined && m.lat !== undefined && m.lon !== undefined) onVertexMove?.(m.index, m.lat, m.lon);
      if (m.type === "vertexSelect" && m.index !== undefined) onVertexSelect?.(m.index);
      if (m.type === "vertexDelete" && m.index !== undefined) onVertexDelete?.(m.index);
      if (m.type === "insertVertex" && m.after !== undefined && m.lat !== undefined && m.lon !== undefined) onInsertVertex?.(m.after, m.lat, m.lon);
    } catch {
      // ignore malformed messages
    }
  };

  return (
    <View style={{ height, borderRadius: 16, overflow: "hidden" }} accessibilityLabel={accessibilityLabel}>
      <WebView
        ref={ref}
        originWhitelist={["*"]}
        source={{ html, baseUrl: "http://localhost/" }}
        onMessage={onMessage}
        javaScriptEnabled
        nestedScrollEnabled
        style={{ flex: 1 }}
      />
    </View>
  );
}
