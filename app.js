const DATA_URL="./data/influenza_history.json";
const GEOJSON_URL="https://raw.githubusercontent.com/smartnews-smri/japan-topography/refs/heads/main/data/municipality/geojson/s0010/N03-21_15_210101.json";

const REGION_MUNICIPALITIES={
"村上":["村上市","関川村","粟島浦村"],
"新発田":["新発田市","阿賀野市","胎内市","聖籠町"],
"新潟市":["新潟市"],
"新津":["五泉市","阿賀町"],
"三条":["三条市","加茂市","燕市","弥彦村","田上町"],
"長岡":["長岡市","小千谷市","見附市","出雲崎町"],
"魚沼":["魚沼市"],
"南魚沼":["南魚沼市","湯沢町"],
"十日町":["十日町市","津南町"],
"柏崎":["柏崎市","刈羽村"],
"上越":["上越市","妙高市"],
"糸魚川":["糸魚川市"],
"佐渡":["佐渡市"]
};
const DISPLAY_REGION={"新潟市":"新潟"};
let allWeeks=[],trendChart=null,latestWeek=null,geoDataPromise=null;

function displayRegionName(name){return DISPLAY_REGION[name]||name}
function n(v,digits=2){if(v===null||v===undefined||Number.isNaN(Number(v)))return"--";return Number(v).toFixed(digits).replace(/\.00$/,"").replace(/(\.\d)0$/,"$1")}
function tierKey(v){if(v>=30)return"purple";if(v>=10)return"red";if(v>=1)return"yellow";return"blue"}
function level(v){
 if(v>=30)return["従来の警報基準相当","warning"];
 if(v>=10)return["従来の注意報基準相当","caution"];
 if(v>=1)return["流行期入りの目安以上","active"];
 return["流行期入りの目安未満","pre"];
}
function color(v){if(v>=30)return"#7b4bb7";if(v>=10)return"#ef6a5b";if(v>=1)return"#f2c94c";return"#0b79b6"}
function municipalityLabel(p){
 const city=(p.N03_003||"").trim(), town=(p.N03_004||"").trim();
 if(city==="新潟市" && town) return `${city}${town}`;
 return town||city||p.name||p.NAME||"";
}
function regionForFeature(p){
 const city=(p.N03_003||"").trim(), town=(p.N03_004||"").trim();
 // 政令指定都市の8区はすべて「新潟」地域として扱う
 if(city==="新潟市") return "新潟市";
 const candidates=[town,city].filter(Boolean);
 for(const [region, municipalities] of Object.entries(REGION_MUNICIPALITIES)){
   if(candidates.some(name=>municipalities.includes(name))) return region;
 }
 return null;
}
function highlightSignal(v){
 const key=v>=30?"warning":v>=10?"caution":v>=1?"active":"pre";
 document.querySelectorAll(".signal-item").forEach(el=>{
   el.classList.toggle("is-current",el.dataset.signal===key);
 });
}
function cleanTopic(t){
 if(!t) return "今週はインフルエンザに関する特記事項は掲載されていません。";
 let s=t
   .replace(/（別紙.*?参照）/g,"")
   .replace(/\r/g,"")
   .replace(/[ \t]+/g," ")
   .replace(/\n+/g,"\n")
   .trim();

 // ○ごとに段落化し、県週報の途中改行を文章としてつなぐ
 const parts=s.split(/[○〇]/).map(x=>x.trim()).filter(Boolean);
 if(!parts.length) return s;

 const head=parts.shift()
   .replace(/\n/g," ")
   .replace(/\s{2,}/g," ")
   .trim();

 const body=parts.map(p=>{
   return "○"+p
     .replace(/\n/g," ")
     .replace(/\s{2,}/g," ")
     .replace(/全県で\s+([0-9.]+)/g,"全県で$1")
     .trim();
 }).join("\n\n");

 return [head,body].filter(Boolean).join("\n\n");
}

async function main(){
 const res=await fetch(DATA_URL,{cache:"no-store"}); if(!res.ok)throw new Error("influenza_history.json を読み込めません");
 const data=await res.json(); allWeeks=(data.weeks||[]).slice().sort((a,b)=>(a.year-b.year)||(a.week-b.week)); if(!allWeeks.length)throw new Error("週データがありません");
 latestWeek=allWeeks.at(-1); const prev=allWeeks.at(-2),prev2=allWeeks.at(-3);
 document.querySelector("#latest-period").textContent=latestWeek.label; document.querySelector("#map-period").textContent=latestWeek.label;
 document.querySelector("#latest-value").textContent=n(latestWeek.prefecture); document.querySelector("#prev-value").textContent=n(prev?.prefecture); document.querySelector("#prev2-value").textContent=n(prev2?.prefecture);
 const wow=prev?.prefecture?((latestWeek.prefecture-prev.prefecture)/prev.prefecture)*100:null; document.querySelector("#wow-value").textContent=wow===null?"--":`${wow>=0?"+":""}${n(wow,1)}%`;
 document.querySelector("#level-badge").textContent=level(latestWeek.prefecture)[0];
 const tier=tierKey(latestWeek.prefecture);
 const badge=document.querySelector("#level-badge");
 badge.classList.remove("tier-blue","tier-yellow","tier-red","tier-purple");
 badge.classList.add(`tier-${tier}`);
 const big=document.querySelector("#latest-value");
 big.classList.remove("tier-blue","tier-yellow","tier-red","tier-purple");
 big.classList.add(`tier-${tier}`);
 highlightSignal(latestWeek.prefecture); document.querySelector("#weekly-topic").textContent=cleanTopic(latestWeek.topic);
 const geo=await fetchGeoData();
 buildHeroSilhouette(geo);
 buildTrendSilhouette(geo);
 renderTrend(13); wireRangeButtons(); renderComparison(allWeeks,latestWeek); renderRanking(latestWeek); renderMap(latestWeek,geo); renderRegionDefinitions(); wireRegionDialog();
}

function renderTrend(weeksCount){
 const visible=allWeeks.slice(-Math.min(weeksCount,allWeeks.length)), labels=visible.map(w=>w.label), values=visible.map(w=>w.prefecture);
 if(trendChart)trendChart.destroy();
 trendChart=new Chart(document.querySelector("#trend-chart"),{type:"line",data:{labels,datasets:[{label:"県全体",data:values,borderColor:"#0b79b6",backgroundColor:"rgba(11,121,182,.10)",pointRadius:3,pointHoverRadius:5,borderWidth:2.6,tension:.22,fill:true}]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>` 定点当たり ${n(c.raw)}`}}},scales:{x:{grid:{display:false},ticks:{maxRotation:0,autoSkip:true,maxTicksLimit:weeksCount<=13?13:weeksCount<=26?13:16,font:{size:10}}},y:{beginAtZero:true,grid:{color:"rgba(90,130,150,.12)"},title:{display:true,text:"定点当たり報告数"}}}}});
 const inner=document.querySelector(".chart-inner"); inner.style.minWidth=weeksCount<=26?"100%":weeksCount<=52?"1250px":"1800px";
 requestAnimationFrame(()=>{const s=document.querySelector("#chart-scroll");s.scrollLeft=s.scrollWidth});
}
function wireRangeButtons(){
 document.querySelectorAll(".range-button").forEach(btn=>btn.addEventListener("click",()=>{document.querySelectorAll(".range-button").forEach(b=>b.classList.remove("active"));btn.classList.add("active");renderTrend(Number(btn.dataset.weeks))}));
 document.querySelector("#to-latest").addEventListener("click",()=>{const s=document.querySelector("#chart-scroll");s.scrollTo({left:s.scrollWidth,behavior:"smooth"})});
}
function renderComparison(weeks,latest){
 const target=weeks.find(w=>w.year===latest.year-1&&w.week===latest.week);
 const thisLabel=document.querySelector("#this-period-label");
 const thisValue=document.querySelector("#this-period-value");
 const lastLabel=document.querySelector("#last-period-label");
 const lastValue=document.querySelector("#last-period-value");

 thisLabel.textContent=`${latest.year} 第${latest.week}週`;
 thisValue.textContent=n(latest.prefecture);
 thisValue.classList.remove("tier-blue","tier-yellow","tier-red","tier-purple");
 thisValue.classList.add(`tier-${tierKey(Number(latest.prefecture))}`);

 if(!target){
   lastLabel.textContent=`${latest.year-1} 同週`;
   lastValue.textContent="--";
   lastValue.classList.remove("tier-blue","tier-yellow","tier-red","tier-purple");
   document.querySelector("#year-compare-note").textContent="前年同週データはまだ蓄積されていません。";
   return;
 }

 lastLabel.textContent=`${target.year} 第${target.week}週`;
 lastValue.textContent=n(target.prefecture);
 lastValue.classList.remove("tier-blue","tier-yellow","tier-red","tier-purple");
 lastValue.classList.add(`tier-${tierKey(Number(target.prefecture))}`);

 const diff=latest.prefecture-target.prefecture;
 document.querySelector("#year-compare-note").textContent=`前年同週より ${diff>=0?"+":""}${n(diff)} ポイント。`;
}
function renderRanking(latest){
 const entries=Object.entries(latest.regions||{}).sort((a,b)=>b[1]-a[1]),box=document.querySelector("#ranking");box.innerHTML="";
 entries.forEach(([name,value],i)=>{
   const row=document.createElement("div");
   const tier=tierKey(Number(value));
   row.className=`rank-row tier-bg-${tier}`;
   row.innerHTML=`<span class="rank-no">${i+1}</span><span class="rank-name">${displayRegionName(name)}</span><span class="rank-value">${n(value)}</span>`;
   box.appendChild(row)
 });
}
function renderRegionDefinitions(){
 const box=document.querySelector("#region-definition-list");box.innerHTML="";
 Object.entries(REGION_MUNICIPALITIES).forEach(([region,municipalities])=>{const item=document.createElement("div");item.className="region-definition-item";item.innerHTML=`<strong>${displayRegionName(region)}</strong><span>${municipalities.join("・")}</span>`;box.appendChild(item)});
}
function wireRegionDialog(){
 const dialog=document.querySelector("#region-dialog");
 document.querySelectorAll(".region-info-button").forEach(btn=>btn.addEventListener("click",()=>dialog.showModal()));
 document.querySelector("#region-dialog-close").addEventListener("click",()=>dialog.close());
 dialog.addEventListener("click",e=>{if(e.target===dialog)dialog.close()});
}

function fetchGeoData(){
 if(!geoDataPromise){
   geoDataPromise=fetch(GEOJSON_URL).then(r=>{if(!r.ok)throw new Error("GeoJSONを読み込めません");return r.json()});
 }
 return geoDataPromise;
}
function geometryRings(geometry){
 if(!geometry) return [];

 // シルエット用途では「各ポリゴンの外周」だけを使う。
 // Polygon: coordinates[0] が外周
 // MultiPolygon: 各 polygon の coordinates[0] がそれぞれの外周
 if(geometry.type==="Polygon"){
   const outer=geometry.coordinates?.[0]||[];
   return outer.length>=3 ? [outer] : [];
 }
 if(geometry.type==="MultiPolygon"){
   return (geometry.coordinates||[])
     .map(poly=>poly?.[0]||[])
     .filter(ring=>ring.length>=3);
 }
 return [];
}
function buildNiigataSilhouetteSvg(geo,{viewW=220,viewH=240,fillId="niigataGradient",opacity=1}={}){
 const rings=[];
 geo.features.forEach(feature=>{
   geometryRings(feature.geometry).forEach(ring=>rings.push(ring));
 });
 if(!rings.length) return "";

 const allPoints=rings.flat();
 let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
 allPoints.forEach(([x,y])=>{
   if(x<minX)minX=x; if(x>maxX)maxX=x; if(y<minY)minY=y; if(y>maxY)maxY=y;
 });
 const width=maxX-minX, height=maxY-minY;
 if(!Number.isFinite(width)||!Number.isFinite(height)||!width||!height) return "";

 const pad=14;
 const scale=Math.min((viewW-pad*2)/width,(viewH-pad*2)/height);
 const offsetX=(viewW-width*scale)/2;
 const offsetY=(viewH-height*scale)/2;
 const toSvgPoint=([x,y])=>{
   const sx=offsetX+(x-minX)*scale;
   const sy=viewH-(offsetY+(y-minY)*scale);
   return `${sx.toFixed(2)} ${sy.toFixed(2)}`;
 };
 const pathData=rings.map(ring=>`M ${ring.map(toSvgPoint).join(" L ")} Z`).join(" ");

 return `
 <svg viewBox="0 0 ${viewW} ${viewH}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
   <defs>
     <linearGradient id="${fillId}" x1="0" y1="0" x2="0.95" y2="1">
       <stop offset="0%" stop-color="#77cbed" />
       <stop offset="100%" stop-color="#177bbf" />
     </linearGradient>
   </defs>
   <path d="${pathData}" fill="url(#${fillId})" fill-opacity="${opacity}" stroke="none" />
 </svg>`;
}

function buildHeroSilhouette(geo){
 const target=document.querySelector("#hero-niigata-silhouette");
 if(!target) return;
 target.innerHTML=buildNiigataSilhouetteSvg(geo,{
   viewW:220,
   viewH:240,
   fillId:"niigataHeroGradient",
   opacity:.9
 });
}

function buildTrendSilhouette(geo){
 const target=document.querySelector("#trend-niigata-watermark");
 if(!target) return;
 target.innerHTML=buildNiigataSilhouetteSvg(geo,{
   viewW:420,
   viewH:390,
   fillId:"niigataTrendGradient",
   opacity:.42
 });
}

async function renderMap(latest,geo){
 const map=L.map("map",{zoomControl:true,attributionControl:true,scrollWheelZoom:false,zoomSnap:0.25,zoomDelta:0.25}).setView([37.55,138.85],8);map.attributionControl.setPrefix(false);
 const layer=L.geoJSON(geo,{style:feature=>{const p=feature.properties||{},region=regionForFeature(p),v=region?Number(latest.regions?.[region]??0):0;return{color:"rgba(255,255,255,.92)",weight:1.2,fillColor:color(v),fillOpacity:.9}},
 onEachFeature:(feature,l)=>{const p=feature.properties||{},m=municipalityLabel(p),region=regionForFeature(p),v=region?Number(latest.regions?.[region]??0):0,regionLabel=region?displayRegionName(region):"地域未対応";l.bindTooltip(`<strong>${m}</strong><br>${regionLabel}${region?`：${n(v)}`:""}`,{sticky:true});l.on({mouseover:e=>e.target.setStyle({weight:2.3,color:"#173f55",fillOpacity:1}),mouseout:e=>layer.resetStyle(e.target)})}}).addTo(map);
 try{
   map.fitBounds(layer.getBounds(),{padding:[4,4]});
   // fitBoundsだけでは余白が大きく見えるため、半段階だけ寄る。
   // 新潟県全体を極端に切らず、画面占有率を高める。
   map.setZoom(map.getZoom()+0.5,{animate:false});
 }catch(e){}
}
main().catch(err=>{console.error(err);document.querySelector("#weekly-topic").textContent="データの読み込みに失敗しました。data/influenza_history.json の配置を確認してください。"});
