/**
 * Self-contained Leaflet page used by MapPicker on web (iframe srcDoc) and native (WebView).
 * Base layers: Esri World Imagery (sub-metre, default for drawing fields); USDA NAIP (US); Sentinel-2 cloudless 10 m (EOX);
 * OpenStreetMap;
 * NASA GIBS MODIS Terra true colour (today); NASA GIBS MODIS 8-day NDVI.
 * Messages out:  {type:"ready"} | {type:"click", lat, lon} | {type:"vertexMove", index, lat, lon}
 * Messages in:   {type:"marker", lat, lon, zoom?} | {type:"polygon", points:[[lon,lat],...], editable?} | {type:"layer", id}
 *                {type:"fit"}  (zoom to the polygon)
 */
export const ESRI_IMAGERY_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
export const ESRI_ATTRIBUTION = "Imagery: Esri, Maxar, Earthstar Geographics, and the GIS User Community";
export const NAIP_URL = "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}";
export const NAIP_ATTRIBUTION = "USDA NAIP / USGS The National Map";
/** NAIP imagery only covers the United States */
export const isUS = (lat: number | null | undefined, lon: number | null | undefined) => lat != null && lon != null && lon < -60 && lat > 20;
export const S2_CLOUDLESS_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{z}/{y}/{x}.jpg";
export const S2_CLOUDLESS_ATTRIBUTION =
  'Sentinel-2 cloudless – <a href="https://s2maps.eu">s2maps.eu</a> by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2023)';

export function leafletHtml(initial: { lat: number; lon: number; zoom: number }): string {
  return `<!doctype html><html><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>html,body,#m{height:100%;margin:0;background:#dfe8d8}.leaflet-container{font:14px system-ui,sans-serif}
.fs-vertex{width:18px!important;height:18px!important;margin:-9px 0 0 -9px!important;border-radius:50%;background:#f2c94c;border:3px solid #fff;box-shadow:0 0 3px rgba(0,0,0,.6)}</style>
</head><body><div id="m" role="application" aria-label="Map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function(){
  function send(o){var s=JSON.stringify(o);
    if(window.ReactNativeWebView){window.ReactNativeWebView.postMessage(s);}
    else if(window.parent&&window.parent!==window){window.parent.postMessage({__fieldshift:true,payload:o},"*");}}
  function isoDaysAgo(n){var d=new Date(Date.now()-n*864e5);return d.toISOString().slice(0,10);}
  var map=L.map("m",{zoomControl:true,attributionControl:true,maxZoom:20}).setView([${initial.lat},${initial.lon}],${initial.zoom});
  var layers={
    street:L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap"}),
    esri:L.tileLayer("${ESRI_IMAGERY_URL}",{maxNativeZoom:19,maxZoom:20,attribution:"${ESRI_ATTRIBUTION}"}),
    naip:L.tileLayer("${NAIP_URL}",{maxNativeZoom:16,maxZoom:20,attribution:"${NAIP_ATTRIBUTION}"}),
    s2:L.tileLayer("${S2_CLOUDLESS_URL}",{maxNativeZoom:15,maxZoom:20,attribution:'${S2_CLOUDLESS_ATTRIBUTION}'}),
    truecolor:L.tileLayer("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/"+isoDaysAgo(2)+"/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg",{maxNativeZoom:9,maxZoom:20,attribution:"NASA GIBS / MODIS Terra"}),
    ndvi:L.tileLayer("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_NDVI_8Day/default/"+isoDaysAgo(20)+"/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png",{maxNativeZoom:9,maxZoom:20,opacity:0.85,attribution:"NASA GIBS / MODIS NDVI 8-day"})
  };
  var current=layers.street.addTo(map);
  var ndviBase=null;
  var marker=null, poly=null, vertices=[];
  function setLayer(id){
    map.removeLayer(current); if(ndviBase){map.removeLayer(ndviBase);ndviBase=null;}
    if(id==="ndvi"){ndviBase=layers.street.addTo(map);}
    current=(layers[id]||layers.street).addTo(map); current.bringToBack(); if(ndviBase)ndviBase.bringToBack();
  }
  function setMarker(lat,lon,zoom){
    if(marker){marker.setLatLng([lat,lon]);} else {marker=L.circleMarker([lat,lon],{radius:9,color:"#ffffff",weight:3,fillColor:"#2f6b3a",fillOpacity:1}).addTo(map);}
    if(zoom){map.setView([lat,lon],Math.max(zoom,map.getZoom()));}
  }
  function setPolygon(points,editable){
    if(poly){map.removeLayer(poly);poly=null;}
    vertices.forEach(function(v){map.removeLayer(v);}); vertices=[];
    if(!points||!points.length)return;
    var ll=points.map(function(p){return [p[1],p[0]];});
    poly=(points.length>=3?L.polygon(ll,{color:"#f2c94c",weight:3,fillOpacity:0.18}):L.polyline(ll,{color:"#f2c94c",weight:3,dashArray:"6,6"})).addTo(map);
    if(editable){
      ll.forEach(function(p,i){
        var m=L.marker(p,{draggable:true,icon:L.divIcon({className:"fs-vertex"}),keyboard:false,title:"Corner "+(i+1)}).addTo(map);
        m.on("drag",function(e){var q=e.target.getLatLng(); var cur=poly.getLatLngs(); var arr=Array.isArray(cur[0])?cur[0]:cur; arr[i]=q; poly.setLatLngs(arr);});
        m.on("dragend",function(e){var q=e.target.getLatLng(); send({type:"vertexMove",index:i,lat:+q.lat.toFixed(6),lon:+q.lng.toFixed(6)});});
        vertices.push(m);
      });
    }
  }
  function fit(){ if(poly){map.fitBounds(poly.getBounds(),{padding:[24,24],maxZoom:18});} }
  function handle(msg){ if(!msg||!msg.type)return;
    if(msg.type==="marker")setMarker(msg.lat,msg.lon,msg.zoom);
    if(msg.type==="polygon")setPolygon(msg.points,msg.editable);
    if(msg.type==="layer")setLayer(msg.id);
    if(msg.type==="fit")fit();
  }
  window.__fieldshiftHandle=handle;
  window.addEventListener("message",function(e){var d=e.data; if(typeof d==="string"){try{d=JSON.parse(d);}catch(_){return;}} if(d&&d.__fieldshiftIn)handle(d.payload);});
  document.addEventListener("message",function(e){try{handle(JSON.parse(e.data));}catch(_){}});
  map.on("click",function(e){send({type:"click",lat:+e.latlng.lat.toFixed(6),lon:+e.latlng.lng.toFixed(6)});});
  send({type:"ready"});
})();
</script></body></html>`;
}

export type MapLayer = "esri" | "naip" | "s2" | "street" | "truecolor" | "ndvi";
export interface MapPickerProps {
  lat: number | null;
  lon: number | null;
  polygon?: [number, number][];
  /** show draggable corner handles (field editor) */
  editable?: boolean;
  layer: MapLayer;
  onPick: (lat: number, lon: number) => void;
  onVertexMove?: (index: number, lat: number, lon: number) => void;
  /** increment to zoom the map to the polygon */
  fitNonce?: number;
  /** initial zoom when a location is known (default 11) */
  zoom?: number;
  height?: number;
  accessibilityLabel: string;
}
