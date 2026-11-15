import React, { useEffect, useMemo, useRef, useState } from "react";
import { View } from "react-native";
import { WebView as RNWebView, type WebViewMessageEvent } from "react-native-webview";
import { terrainHtml, type TerrainMapProps } from "./terrainHtml";

type WebViewHandle = { injectJavaScript: (js: string) => void };
const WebView = RNWebView as unknown as React.ComponentType<{
  ref?: React.Ref<WebViewHandle>;
  originWhitelist: string[];
  source: { html: string; baseUrl?: string };
  onMessage: (e: WebViewMessageEvent) => void;
  javaScriptEnabled?: boolean;
  nestedScrollEnabled?: boolean;
  mixedContentMode?: "always" | "never" | "compatibility";
  style?: object;
}>;

/** Native terrain map (iOS/Android): Leaflet inside a WebView. Web uses TerrainMap.web.tsx. */
export default function TerrainMap({ lat, lon, polygon, base, overlay, opacity, onOverlayError, fitNonce, height = 380, accessibilityLabel }: TerrainMapProps) {
  const ref = useRef<WebViewHandle>(null);
  const [ready, setReady] = useState(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const html = useMemo(() => terrainHtml({ lat, lon }), []);
  const post = (payload: object) => ref.current?.injectJavaScript(`window.__fieldshiftHandle(${JSON.stringify(payload)});true;`);
  useEffect(() => {
    if (ready) post({ type: "field", lat, lon, polygon: polygon ?? [] });
  }, [ready, lat, lon, polygon]);
  useEffect(() => {
    if (ready) post({ type: "base", id: base });
  }, [ready, base]);
  useEffect(() => {
    if (ready) post({ type: "overlay", url: overlay?.url ?? null, bounds: overlay?.bounds, opacity, attribution: overlay?.attribution });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, overlay?.url]);
  useEffect(() => {
    if (ready) post({ type: "opacity", value: opacity });
  }, [ready, opacity]);
  useEffect(() => {
    if (ready && fitNonce) post({ type: "fit" });
  }, [ready, fitNonce]);
  const onMessage = (e: WebViewMessageEvent) => {
    try {
      const m = JSON.parse(e.nativeEvent.data) as { type: string };
      if (m.type === "ready") setReady(true);
      if (m.type === "overlayError") onOverlayError?.();
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
        mixedContentMode="always"
        style={{ flex: 1 }}
      />
    </View>
  );
}
