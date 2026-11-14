/**
 * Self-contained Leaflet page used by MapPicker on web (iframe srcDoc) and native (WebView).
 * Base layers: OpenStreetMap, NASA GIBS MODIS Terra true colour, NASA GIBS MODIS 8-day NDVI.
 * Messages out:  {type:"ready"} | {type:"click", lat, lon}
 * Messages in:   {type:"marker", lat, lon, zoom?} | {type:"polygon", points:[[lon,lat],...]} | {type:"layer", id}
 */
export function leafletHtml(initial: { lat: number; lon: number; zoom: number }): string {
  return `<!doctype html><html><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>html,body,#m{height:100%;margin:0;background:#dfe8d8}.leaflet-container{font:14px system-ui,sans-serif}</style>
</head><body><div id="m" role="application" aria-label="Map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function(){
  function send(o){var s=JSON.stringify(o);
    if(window.ReactNativeWebView){window.ReactNativeWebView.postMessage(s);}
    else if(window.parent&&window.parent!==window){window.parent.postMessage({__fieldshift:true,payload:o},"*");}}
  function isoDaysAgo(n){var d=new Date(Date.now()-n*864e5);return d.toISOString().slice(0,10);}
  var map=L.map("m",{zoomControl:true,attributionControl:true}).setView([${initial.lat},${initial.lon}],${initial.zoom});
  var layers={
    street:L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap"}),
    truecolor:L.tileLayer("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/"+isoDaysAgo(2)+"/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg",{maxNativeZoom:9,maxZoom:16,attribution:"NASA GIBS / MODIS Terra"}),
    ndvi:L.tileLayer("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_NDVI_8Day/default/"+isoDaysAgo(20)+"/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png",{maxNativeZoom:9,maxZoom:16,opacity:0.85,attribution:"NASA GIBS / MODIS NDVI 8-day"})
  };
  var current=layers.street.addTo(map);
  var ndviBase=null;
  var marker=null, poly=null;
  function setLayer(id){
    map.removeLayer(current); if(ndviBase){map.removeLayer(ndviBase);ndviBase=null;}
    if(id==="ndvi"){ndviBase=layers.street.addTo(map);}
    current=(layers[id]||layers.street).addTo(map);
  }
  function setMarker(lat,lon,zoom){
    if(marker){marker.setLatLng([lat,lon]);} else {marker=L.circleMarker([lat,lon],{radius:9,color:"#ffffff",weight:3,fillColor:"#2f6b3a",fillOpacity:1}).addTo(map);}
    if(zoom){map.setView([lat,lon],zoom);}
  }
  function setPolygon(points){
    if(poly){map.removeLayer(poly);poly=null;}
    if(points&&points.length){poly=L.polygon(points.map(function(p){return [p[1],p[0]];}),{color:"#f2c94c",weight:3,fillOpacity:0.15}).addTo(map);}
  }
  function handle(msg){ if(!msg||!msg.type)return;
    if(msg.type==="marker")setMarker(msg.lat,msg.lon,msg.zoom);
    if(msg.type==="polygon")setPolygon(msg.points);
    if(msg.type==="layer")setLayer(msg.id);
  }
  window.__fieldshiftHandle=handle;
  window.addEventListener("message",function(e){var d=e.data; if(typeof d==="string"){try{d=JSON.parse(d);}catch(_){return;}} if(d&&d.__fieldshiftIn)handle(d.payload);});
  document.addEventListener("message",function(e){try{handle(JSON.parse(e.data));}catch(_){}});
  map.on("click",function(e){send({type:"click",lat:+e.latlng.lat.toFixed(5),lon:+e.latlng.lng.toFixed(5)});});
  send({type:"ready"});
})();
</script></body></html>`;
}

export type MapLayer = "street" | "truecolor" | "ndvi";
export interface MapPickerProps {
  lat: number | null;
  lon: number | null;
  polygon?: [number, number][];
  layer: MapLayer;
  onPick: (lat: number, lon: number) => void;
  height?: number;
  accessibilityLabel: string;
}
