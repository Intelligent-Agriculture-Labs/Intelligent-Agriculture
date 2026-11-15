/* eslint-disable import/no-named-as-default-member -- i18n.t on the shared instance, as in i18n/index.ts */
import i18n from "i18next";
import { ESRI_ATTRIBUTION, ESRI_IMAGERY_URL, NAIP_ATTRIBUTION, NAIP_URL, S2_CLOUDLESS_ATTRIBUTION, S2_CLOUDLESS_URL } from "./leafletHtml";

/**
 * Leaflet page for the Map tab (web: iframe srcDoc, native: WebView).
 * Base layers: OpenStreetMap, NASA GIBS MODIS true colour, NASA GIBS MODIS 8-day NDVI.
 * Messages in:  {type:"base", id} | {type:"overlay", url, bounds:[[s,w],[n,e]], opacity} | {type:"overlay", url:null}
 *               {type:"opacity", value} | {type:"field", lat, lon, polygon:[[lon,lat],...]}
 * Messages out: {type:"ready"} | {type:"overlayError"}
 */
/** Escape a translated label for an HTML attribute. */
const attr = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

export function terrainHtml(initial: { lat: number; lon: number }): string {
  return `<!doctype html><html><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>html,body,#m{height:100%;margin:0;background:#dfe8d8}.leaflet-container{font:14px system-ui,sans-serif}</style>
</head><body><div id="m" role="application" aria-label="${attr(i18n.t("map.a11yTerrain"))}"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function(){
  function send(o){var s=JSON.stringify(o);
    if(window.ReactNativeWebView){window.ReactNativeWebView.postMessage(s);}
    else if(window.parent&&window.parent!==window){window.parent.postMessage({__fieldshift:true,payload:o},"*");}}
  function isoDaysAgo(n){var d=new Date(Date.now()-n*864e5);return d.toISOString().slice(0,10);}
  var map=L.map("m",{zoomControl:true,attributionControl:true,maxZoom:20}).setView([${initial.lat},${initial.lon}],13);
  var bases={
    street:L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap"}),
    esri:L.tileLayer("${ESRI_IMAGERY_URL}",{maxNativeZoom:19,maxZoom:20,attribution:"${ESRI_ATTRIBUTION}"}),
    naip:L.tileLayer("${NAIP_URL}",{maxNativeZoom:16,maxZoom:20,attribution:"${NAIP_ATTRIBUTION}"}),
    s2:L.tileLayer("${S2_CLOUDLESS_URL}",{maxNativeZoom:15,maxZoom:20,attribution:'${S2_CLOUDLESS_ATTRIBUTION}'}),
    truecolor:L.tileLayer("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/"+isoDaysAgo(2)+"/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg",{maxNativeZoom:9,maxZoom:17,attribution:"NASA GIBS / MODIS Terra"}),
    ndvi:L.tileLayer("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_NDVI_8Day/default/"+isoDaysAgo(20)+"/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png",{maxNativeZoom:9,maxZoom:17,opacity:0.85,attribution:"NASA GIBS / MODIS NDVI 8-day"})
  };
  var base=bases.street.addTo(map), ndviUnder=null, overlay=null, field=null, pin=null, opacity=0.75, fitted=false;
  function setBase(id){
    map.removeLayer(base); if(ndviUnder){map.removeLayer(ndviUnder);ndviUnder=null;}
    if(id==="ndvi"){ndviUnder=bases.street.addTo(map);}
    base=(bases[id]||bases.street).addTo(map); base.bringToBack(); if(ndviUnder)ndviUnder.bringToBack();
  }
  var attrib=null;
  function setOverlay(url,bounds,op,at){
    attrib=at||null;
    if(overlay){map.removeLayer(overlay);overlay=null;}
    if(!url)return;
    if(op!==undefined&&op!==null)opacity=op;
    overlay=L.imageOverlay(url,bounds,{opacity:opacity,interactive:false,attribution:attrib||"Terrain: NASA SRTM / USGS 3DEP via AWS Terrain Tiles"}).addTo(map);
    overlay.on("error",function(){send({type:"overlayError"});});
    if(field)field.bringToFront();
    if(!fitted){map.fitBounds(bounds,{padding:[4,4]});map.setZoom(Math.max(map.getZoom(),13));fitted=true;}
  }
  function setField(lat,lon,poly){
    if(field){map.removeLayer(field);field=null;} if(pin){map.removeLayer(pin);pin=null;}
    if(poly&&poly.length>=3){field=L.polygon(poly.map(function(p){return [p[1],p[0]];}),{color:"#ffffff",weight:3,fill:false,dashArray:"6,4"}).addTo(map);}
    else{field=L.circle([lat,lon],{radius:150,color:"#ffffff",weight:3,fill:false,dashArray:"6,4"}).addTo(map);}
    pin=L.circleMarker([lat,lon],{radius:6,color:"#ffffff",weight:2,fillColor:"#17241a",fillOpacity:1}).addTo(map);
  }
  function handle(m){ if(!m||!m.type)return;
    if(m.type==="base")setBase(m.id);
    if(m.type==="overlay")setOverlay(m.url,m.bounds,m.opacity,m.attribution);
    if(m.type==="fit"&&field){map.fitBounds(field.getBounds(),{padding:[20,20],maxZoom:17});}
    if(m.type==="opacity"){opacity=m.value; if(overlay)overlay.setOpacity(m.value);}
    if(m.type==="field")setField(m.lat,m.lon,m.polygon);
  }
  window.__fieldshiftHandle=handle;
  window.addEventListener("message",function(e){var d=e.data; if(typeof d==="string"){try{d=JSON.parse(d);}catch(_){return;}} if(d&&d.__fieldshiftIn)handle(d.payload);});
  document.addEventListener("message",function(e){try{handle(JSON.parse(e.data));}catch(_){}});
  send({type:"ready"});
})();
</script></body></html>`;
}

export type BaseLayer = "esri" | "naip" | "s2" | "street" | "truecolor" | "ndvi";
export interface TerrainMapProps {
  lat: number;
  lon: number;
  polygon?: [number, number][];
  base: BaseLayer;
  overlay: { url: string; bounds: [[number, number], [number, number]]; attribution?: string } | null;
  /** increment to zoom to the field outline */
  fitNonce?: number;
  opacity: number;
  onOverlayError?: () => void;
  height?: number;
  accessibilityLabel: string;
}
