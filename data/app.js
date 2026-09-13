const DATA_URL="./data/influenza_history.json";
const AI_COMMENT_URL="./data/ai_comment.json";
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
let allWeeks=[],trendChart=null,latestWeek=null,geoDataPromise=null,mapInstance=null,mapGeoLayer=null,currentMapWeek=null,mapPlayTimer=null,mapRangeStartIndex=0,mapRangeWeeks=52;

function displayRegionName(name){return DISPLAY_REGION[name]||name}
function compareHeading(w){return w ? `${w.year} 第${w.week}週${w.label?`（${w.label}）`:""}` : "--"}
function n(v,digits=2){if(v===null||v===undefined||Number.isNaN(Number(v)))return"--";return Number(v).toFixed(digits).replace(/\.00$/,"").replace(/(\.\d)0$/,"$1")}

function absoluteWeekDiff(current, previous){
  const c = Number(current);
  const p = Number(previous);
  if(!Number.isFinite(c) || !Number.isFinite(p)) return null;
  return +(c - p).toFixed(2);
}

function formatSignedPerSentinel(value){
  const v = Number(value);
  if(!Number.isFinite(v)) return "-";
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${sign}${Math.abs(v).toFixed(2).replace(/\.00$/,"").replace(/(\.\d)0$/,"$1")}人／定点`;
}

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
 const wow=prev?.prefecture?((latestWeek.prefecture-prev.prefecture)/prev.prefecture)*100:null; document.querySelector("#wow-value").textContent=wow===null?"--":`${wow>=0?"+":""}${formatSignedPerSentinel(absoluteWeekDiff(latest.prefecture, prev.prefecture))}`;
 document.querySelector("#level-badge").textContent=level(latestWeek.prefecture)[0];
 const tier=tierKey(latestWeek.prefecture);
 const badge=document.querySelector("#level-badge");
 badge.classList.remove("tier-blue","tier-yellow","tier-red","tier-purple");
 badge.classList.add(`tier-${tier}`);
 const big=document.querySelector("#latest-value");
 big.classList.remove("tier-blue","tier-yellow","tier-red","tier-purple");
 big.classList.add(`tier-${tier}`);
 highlightSignal(latestWeek.prefecture); await renderWeeklyInsight(latestWeek);
 const geo=await fetchGeoData();
 buildHeroSilhouette(geo);
 buildTrendSilhouette(geo);
 renderTrend(13); wireRangeButtons(); renderComparison(allWeeks,latestWeek); renderRanking(latestWeek); renderMap(latestWeek,geo); wireMapTimeline(); renderRegionDefinitions(); wireRegionDialog();
}

async function renderWeeklyInsight(latest){
 const box=document.querySelector("#weekly-topic");
 const source=document.querySelector("#weekly-source");
 const note=document.querySelector("#ai-topic-note");
 if(!box) return;

 try{
   const res=await fetch(AI_COMMENT_URL,{cache:"no-store"});
   if(!res.ok) throw new Error("AIコメント未生成");
   const ai=await res.json();

   const src=ai.source_week||{};
   const sameWeek=Number(src.year)===Number(latest.year) && Number(src.week)===Number(latest.week);
   if(!sameWeek) throw new Error("AIコメントが最新週ではありません");

   box.innerHTML="";

   if(ai.headline){
     const lead=document.createElement("p");
     lead.className="ai-insight-headline";
     lead.textContent=ai.headline;
     box.appendChild(lead);
   }

   [
     ["概況",ai.summary],
     ["推移",ai.trend],
     ["地域",ai.regional],
     ["前年同期",ai.year_on_year]
   ].forEach(([label,text])=>{
     if(!text) return;
     const p=document.createElement("p");
     p.className="ai-insight-paragraph";

     const tag=document.createElement("span");
     tag.className="ai-insight-label";
     tag.textContent=label;

     const body=document.createElement("span");
     body.textContent=text;

     p.append(tag,body);
     box.appendChild(p);
   });

   if(source) source.textContent="AI自動生成";
   if(note){
     note.textContent=ai.disclaimer||"新潟県公表データをもとにAIが自動生成した分析コメントです。";
     note.hidden=false;
   }
 }catch(err){
   // API生成前・通信失敗時は従来の県週報トピックに自動フォールバック
   box.textContent=cleanTopic(latest.topic);
   if(source) source.textContent="新潟県週報";
   if(note) note.hidden=true;
 }
}

function renderTrend(weeksCount){
 const visible=allWeeks.slice(-Math.min(weeksCount,allWeeks.length));
 const labels=visible.map(w=>w.label);
 const values=visible.map(w=>w.prefecture);

 // 3か月・半年・1年では、各週と同じ「前年の週番号」を重ねて比較する
 const showPreviousYear=[13,26,52].includes(weeksCount);
 const previousValues=showPreviousYear
   ? visible.map(w=>{
       const prev=allWeeks.find(x=>x.year===w.year-1&&x.week===w.week);
       return prev ? prev.prefecture : null;
     })
   : [];

 if(trendChart)trendChart.destroy();

 const datasets=[
   {
     label:`今年（${latestWeek.year}）`,
     data:values,
     borderColor:"#0b79b6",
     backgroundColor:"rgba(11,121,182,.10)",
     pointRadius:3,
     pointHoverRadius:5,
     borderWidth:2.8,
     tension:.22,
     fill:true
   }
 ];

 if(showPreviousYear){
   datasets.push({
     label:"前年同期",
     data:previousValues,
     borderColor:"#8fa3b1",
     backgroundColor:"transparent",
     pointRadius:2.4,
     pointHoverRadius:4,
     borderWidth:2.2,
     borderDash:[7,5],
     tension:.22,
     fill:false,
     spanGaps:false
   });
 }

 trendChart=new Chart(document.querySelector("#trend-chart"),{
   type:"line",
   data:{labels,datasets},
   options:{
     responsive:true,
     maintainAspectRatio:false,
     interaction:{mode:"index",intersect:false},
     plugins:{
       legend:{
         display:showPreviousYear,
         position:"top",
         align:"end",
         labels:{
           usePointStyle:true,
           boxWidth:8,
           boxHeight:8,
           padding:16,
           font:{size:11,weight:"700"}
         }
       },
       tooltip:{
         callbacks:{
           label:c=>` ${c.dataset.label}：定点当たり ${n(c.raw)}`
         }
       }
     },
     scales:{
       x:{
         grid:{display:false},
         ticks:{
           maxRotation:0,
           autoSkip:true,
           maxTicksLimit:weeksCount<=13?13:weeksCount<=26?13:16,
           font:{size:10}
         }
       },
       y:{
         beginAtZero:true,
         grid:{color:"rgba(90,130,150,.12)"},
         title:{display:true,text:"定点当たり報告数"}
       }
     }
   }
 });

 const inner=document.querySelector(".chart-inner");
 inner.style.minWidth=weeksCount<=26?"100%":weeksCount<=52?"1250px":"1800px";
 requestAnimationFrame(()=>{
   const s=document.querySelector("#chart-scroll");
   s.scrollLeft=s.scrollWidth;
 });
}
function wireRangeButtons(){
 document.querySelectorAll(".range-button").forEach(btn=>btn.addEventListener("click",()=>{document.querySelectorAll(".range-button").forEach(b=>b.classList.remove("active"));btn.classList.add("active");renderTrend(Number(btn.dataset.weeks))}));
 document.querySelector("#to-latest").addEventListener("click",()=>{const s=document.querySelector("#chart-scroll");s.scrollTo({left:s.scrollWidth,behavior:"smooth"})});
}
function renderComparison(weeks,latest){
 const list=document.querySelector("#comparison-list");
 const note=document.querySelector("#year-compare-note");
 list.innerHTML="";

 const latestIndex=weeks.findIndex(w=>w.year===latest.year&&w.week===latest.week);
 const recent=(latestIndex>=0?weeks.slice(Math.max(0,latestIndex-4),latestIndex+1):[latest]).reverse();

 recent.forEach((current,idx)=>{
   const target=weeks.find(w=>w.year===current.year-1&&w.week===current.week);
   const currentTier=tierKey(Number(current.prefecture));

   const row=document.createElement("div");
   row.className="comparison-row";

   const head=document.createElement("div");
   head.className="comparison-row-head";
   head.innerHTML=`<span class="comparison-row-badge ${idx===0?"compare-badge-alert-blink":""}">${idx===0?"最新":"過去"}</span><span class="comparison-row-week">第${current.week}週</span>`;

   const body=document.createElement("div");
   body.className="comparison-body";

   const prevWrap=document.createElement("div");
   prevWrap.className="compare-period";
   const prevLabel=document.createElement("span");
   prevLabel.className="compare-label";
   prevLabel.textContent=target?compareHeading(target):`${current.year-1} 同週`;
   const prevValue=document.createElement("strong");
   prevValue.className="compare-value";
   if(target){
     prevValue.textContent=n(target.prefecture);
     prevValue.classList.add(`tier-${tierKey(Number(target.prefecture))}`);
   }else{
     prevValue.textContent="--";
   }
   prevWrap.append(prevLabel,prevValue);

   const arrow=document.createElement("div");
   arrow.className="compare-arrow";
   arrow.textContent="→";

   const currWrap=document.createElement("div");
   currWrap.className="compare-period";
   const currLabel=document.createElement("span");
   currLabel.className="compare-label";
   currLabel.textContent=compareHeading(current);
   const currValue=document.createElement("strong");
   currValue.className="compare-value";
   currValue.textContent=n(current.prefecture);
   currValue.classList.add(`tier-${currentTier}`);
   currWrap.append(currLabel,currValue);

   body.append(prevWrap,arrow,currWrap);

   const foot=document.createElement("div");
   foot.className="comparison-row-note";
   if(target){
     const diff=Number(current.prefecture)-Number(target.prefecture);
     foot.textContent=`前年差 ${diff>=0?"+":""}${n(diff)} ポイント`;
     foot.classList.add(`tier-${currentTier}`);
   }else{
     foot.textContent="前年同週データなし";
   }

   row.append(head,body,foot);
   list.appendChild(row);
 });

 const topCurrent=recent[0];
 const topTarget=weeks.find(w=>w.year===topCurrent.year-1&&w.week===topCurrent.week);
 if(topTarget){
   const diff=Number(topCurrent.prefecture)-Number(topTarget.prefecture);
   note.textContent=`最新の ${compareHeading(topCurrent)} は、前年同週より ${diff>=0?"+":""}${n(diff)} ポイントです。`;
 }else{
   note.textContent="最新週の前年同週データはまだ蓄積されていません。";
 }
}
function renderRanking(weekData){
 const entries=Object.entries(weekData.regions||{}).sort((a,b)=>b[1]-a[1]);
 const box=document.querySelector("#ranking");
 box.innerHTML="";
 const period=document.querySelector("#ranking-period");
 if(period) period.textContent=weekData.label||`${weekData.year} 第${weekData.week}週`;

 entries.forEach(([name,value],i)=>{
   const row=document.createElement("div");
   const tier=tierKey(Number(value));
   row.className=`rank-row tier-bg-${tier}`;
   row.innerHTML=`<span class="rank-no">${i+1}</span><span class="rank-name">${displayRegionName(name)}</span><span class="rank-value">${n(value)}</span>`;
   box.appendChild(row);
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
 currentMapWeek=latest;
 mapInstance=L.map("map",{zoomControl:true,attributionControl:true,scrollWheelZoom:false,zoomSnap:0.25,zoomDelta:0.25}).setView([37.55,138.85],8);
 mapInstance.attributionControl.setPrefix(false);

 // 再生中でも「いま何週か」を地図上で確認できる週表示
 const mapEl=document.querySelector("#map");
 if(mapEl&&!mapEl.querySelector("#map-week-overlay")){
   const overlay=document.createElement("div");
   overlay.id="map-week-overlay";
   overlay.className="map-week-overlay";
   overlay.setAttribute("aria-live","polite");
   mapEl.appendChild(overlay);
 }

 const styleForFeature=feature=>{
   const p=feature.properties||{};
   const region=regionForFeature(p);
   const v=region?Number(currentMapWeek?.regions?.[region]??0):0;
   return{
     color:"rgba(255,255,255,.92)",
     weight:1.2,
     fillColor:color(v),
     fillOpacity:.9
   };
 };

 mapGeoLayer=L.geoJSON(geo,{
   style:styleForFeature,
   onEachFeature:(feature,l)=>{
     l.on({
       mouseover:e=>e.target.setStyle({weight:2.3,color:"#173f55",fillOpacity:1}),
       mouseout:e=>mapGeoLayer.resetStyle(e.target)
     });
   }
 }).addTo(mapInstance);

 updateMapLayerContent(latest);

 try{
   mapInstance.fitBounds(mapGeoLayer.getBounds(),{padding:[4,4]});
   mapInstance.setZoom(mapInstance.getZoom()+0.5,{animate:false});
 }catch(e){}
}

function updateMapLayerContent(weekData){
 if(!weekData||!mapGeoLayer) return;
 currentMapWeek=weekData;

 mapGeoLayer.eachLayer(l=>{
   const p=l.feature?.properties||{};
   const municipality=municipalityLabel(p);
   const region=regionForFeature(p);
   const value=region?Number(weekData.regions?.[region]??0):0;
   const regionLabel=region?displayRegionName(region):"地域未対応";

   l.setStyle({
     color:"rgba(255,255,255,.92)",
     weight:1.2,
     fillColor:color(value),
     fillOpacity:.9
   });
   l.bindTooltip(
     `<strong>${municipality}</strong><br>${regionLabel}${region?`：${n(value)}`:""}<br><span style="font-size:11px;color:#687f8d">${weekData.label||""}</span>`,
     {sticky:true}
   );
 });

 const period=document.querySelector("#map-period");
 if(period) period.textContent=weekData.label||`${weekData.year} 第${weekData.week}週`;
 const selected=document.querySelector("#map-selected-period");
 const weekText=`${weekData.year} 第${weekData.week}週（${weekData.label||""}）`;
 if(selected) selected.textContent=weekText;

 const mapOverlay=document.querySelector("#map-week-overlay");
 if(mapOverlay) mapOverlay.textContent=weekText;

 renderRanking(weekData);
}

function stopMapPlayback(){
 if(mapPlayTimer){
   clearInterval(mapPlayTimer);
   mapPlayTimer=null;
 }
 const play=document.querySelector("#map-play");
 if(play) play.textContent="▶ 再生";
}

function setMapWeekIndex(index,{stopPlayback=true}={}){
 const slider=document.querySelector("#map-week-slider");
 const min=mapRangeStartIndex;
 const max=allWeeks.length-1;
 const clamped=Math.max(min,Math.min(max,Number(index)));
 if(stopPlayback) stopMapPlayback();
 if(slider) slider.value=String(clamped);
 updateMapLayerContent(allWeeks[clamped]);
}

function applyMapRange(rangeValue,{jumpToLatest=true}={}){
 const slider=document.querySelector("#map-week-slider");
 if(!slider||!allWeeks.length) return;

 stopMapPlayback();

 mapRangeWeeks=rangeValue==="all" ? "all" : Number(rangeValue);
 const total=allWeeks.length;
 mapRangeStartIndex=mapRangeWeeks==="all" ? 0 : Math.max(0,total-mapRangeWeeks);

 slider.min=String(mapRangeStartIndex);
 slider.max=String(total-1);

 const first=document.querySelector("#map-first-week");
 const last=document.querySelector("#map-last-week");
 const firstWeek=allWeeks[mapRangeStartIndex];
 const lastWeek=allWeeks.at(-1);

 if(first) first.textContent=`${firstWeek.year} 第${firstWeek.week}週`;
 if(last) last.textContent=`${lastWeek.year} 第${lastWeek.week}週`;

 document.querySelectorAll(".map-range-button").forEach(btn=>{
   const v=btn.dataset.mapRange;
   const active=(mapRangeWeeks==="all"&&v==="all")||(String(mapRangeWeeks)===v);
   btn.classList.toggle("is-active",active);
   btn.setAttribute("aria-pressed",active?"true":"false");
 });

 if(jumpToLatest){
   slider.value=String(total-1);
   updateMapLayerContent(lastWeek);
 }else{
   const current=Math.max(mapRangeStartIndex,Number(slider.value));
   slider.value=String(current);
   updateMapLayerContent(allWeeks[current]);
 }
}

function wireMapTimeline(){
 const slider=document.querySelector("#map-week-slider");
 const play=document.querySelector("#map-play");
 const prev=document.querySelector("#map-prev-week");
 const next=document.querySelector("#map-next-week");
 const latest=document.querySelector("#map-latest");
 const rangeButtons=[...document.querySelectorAll(".map-range-button")];
 if(!slider||!play||!prev||!next||!latest||!allWeeks.length) return;

 applyMapRange(52);

 slider.addEventListener("input",()=>setMapWeekIndex(Number(slider.value)));

 prev.addEventListener("click",()=>setMapWeekIndex(Number(slider.value)-1));
 next.addEventListener("click",()=>setMapWeekIndex(Number(slider.value)+1));
 latest.addEventListener("click",()=>setMapWeekIndex(allWeeks.length-1));

 rangeButtons.forEach(btn=>{
   btn.addEventListener("click",()=>applyMapRange(btn.dataset.mapRange));
 });

 play.addEventListener("click",()=>{
   if(mapPlayTimer){
     stopMapPlayback();
     return;
   }

   let index=Number(slider.value);

   if(index>=allWeeks.length-1){
     index=mapRangeStartIndex;
     setMapWeekIndex(index,{stopPlayback:false});
   }

   play.textContent="Ⅱ 一時停止";
   mapPlayTimer=setInterval(()=>{
     index=Number(slider.value)+1;
     if(index>=allWeeks.length){
       setMapWeekIndex(allWeeks.length-1,{stopPlayback:false});
       stopMapPlayback();
       return;
     }
     setMapWeekIndex(index,{stopPlayback:false});
   },700);
 });
}
main().catch(err=>{console.error(err);document.querySelector("#weekly-topic").textContent="データの読み込みに失敗しました。data/influenza_history.json の配置を確認してください。"});
