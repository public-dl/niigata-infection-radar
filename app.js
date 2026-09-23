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
const REGION_ORDER=["新潟市","新発田","新津","三条","長岡","魚沼","南魚沼","十日町","柏崎","糸魚川","村上","佐渡","上越"];
const REGION_TITLE_SUFFIX=new Set(["新発田","新津","三条","長岡","魚沼","南魚沼","十日町","柏崎","糸魚川","村上","佐渡","上越"]);
let allWeeks=[],trendChart=null,latestWeek=null,geoDataPromise=null,mapInstance=null,mapGeoLayer=null,currentMapWeek=null,mapPlayTimer=null,mapRangeStartIndex=0,mapRangeWeeks=13;
let trendWeeks=13,trendRegion="prefecture",trendComparePrefecture=true,weeklyAIData=null,weeklyAIAudience="general";
let ageLatestChart=null,ageLatestWeekIndex=0,ageSeriesChart=null,ageHeatmapTimer=null,ageHeatmapRange=13,ageHeatmapEndIndex=0,ageSeriesWeeks=13;
const AGE_GROUPS=["0歳","1～4歳","5～9歳","10～14歳","15～19歳","20～59歳","60歳以上"];
const AGE_COLORS={
  "0歳":"#76b7e5",
  "1～4歳":"#196fbd",
  "5～9歳":"#18a8b8",
  "10～14歳":"#45a86b",
  "15～19歳":"#e1a72c",
  "20～59歳":"#e47a3f",
  "60歳以上":"#d95d94"
};
const ageSeriesVisible=new Set(AGE_GROUPS);

function displayRegionName(name){return DISPLAY_REGION[name]||name}
function compareHeading(w){return w ? `${w.year} 第${w.week}週${w.label?`（${w.label}）`:""}` : "--"}
function n(v,digits=2){if(v===null||v===undefined||Number.isNaN(Number(v)))return"--";return Number(v).toFixed(digits).replace(/\.00$/,"").replace(/(\.\d)0$/,"$1")}

function formatUpdatedAt(value){
 if(!value)return"--";
 const d=new Date(value);
 if(Number.isNaN(d.getTime()))return String(value);
 const parts=new Intl.DateTimeFormat("ja-JP",{timeZone:"Asia/Tokyo",year:"numeric",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hour12:false}).formatToParts(d);
 const get=t=>parts.find(x=>x.type===t)?.value||"";
 return `${get("year")}/${get("month")}/${get("day")} ${get("hour")}:${get("minute")}`;
}

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
 if(v>=30)return["従来の警報基準\n相当","warning"];
 if(v>=10)return["従来の注意報基準\n相当","caution"];
 if(v>=1)return["流行期入りの目安\n以上","active"];
 return["流行期入りの目安\n未満","pre"];
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
function updateHeroSignal(v){
 const tier=tierKey(Number(v));
 const lights=document.querySelector("#hero-signal-lights");
 if(!lights) return;

 lights.querySelectorAll(".hero-signal-dot").forEach(dot=>dot.classList.remove("is-active"));

 const active=lights.querySelector(`.signal-${tier}`);
 if(active) active.classList.add("is-active");

 lights.classList.remove("tier-blue","tier-yellow","tier-red","tier-purple");
 lights.classList.add(`tier-${tier}`);
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



// ---------- 年代別統計 ----------
function ageRate(week,group){
  const v=week?.age_per_sentinel?.[group];
  return Number.isFinite(Number(v))?Number(v):null;
}
function ageCount(week,group){
  const v=week?.age_counts?.[group];
  return Number.isFinite(Number(v))?Number(v):null;
}
function ageWeekShort(w){
  if(!w) return "--";
  return `${w.year} W${String(w.week).padStart(2,"0")}`;
}
function stopAgeHeatmapPlayback(){
  if(ageHeatmapTimer){clearInterval(ageHeatmapTimer);ageHeatmapTimer=null;}
  const play=document.querySelector("#age-play");
  if(play) play.textContent="▶ 再生";
}
function ageRowMax(group){
  return Math.max(0,...allWeeks.map(w=>ageRate(w,group)||0));
}
function ageHeatColor(value,max){
  if(value===null||value===undefined) return "rgba(11,121,182,.025)";
  if(max<=0) return "rgba(11,121,182,.025)";
  const ratio=Math.max(0,Math.min(1,value/max));
  const alpha=.045 + Math.pow(ratio,.72)*.91;
  return `rgba(11,121,182,${alpha.toFixed(3)})`;
}
function renderAgeHeatmap(endIndex=ageHeatmapEndIndex){
  const host=document.querySelector("#age-heatmap");
  if(!host||!allWeeks.length) return;
  ageHeatmapEndIndex=Math.max(0,Math.min(allWeeks.length-1,endIndex));
  const count=Math.min(ageHeatmapRange,ageHeatmapEndIndex+1);
  const start=Math.max(0,ageHeatmapEndIndex-count+1);
  const visible=allWeeks.slice(start,ageHeatmapEndIndex+1);
  host.style.setProperty("--age-cols",String(visible.length));
  host.innerHTML="";

  const header=document.createElement("div");
  header.className="age-heatmap-row age-heatmap-header";
  const corner=document.createElement("div");corner.className="age-heatmap-label";corner.textContent="年代 / 週";header.appendChild(corner);
  visible.forEach((w,i)=>{
    const el=document.createElement("div");el.className="age-heatmap-week";
    const show=i===0||i===visible.length-1||w.week===1||i%4===0;
    el.textContent=show?`W${w.week}`:"";
    el.title=`${w.year}年第${w.week}週 ${w.label||""}`;
    header.appendChild(el);
  });
  host.appendChild(header);

  AGE_GROUPS.forEach(group=>{
    const row=document.createElement("div");row.className="age-heatmap-row";
    const label=document.createElement("div");label.className="age-heatmap-label";label.textContent=group;row.appendChild(label);
    const max=ageRowMax(group);
    visible.forEach((w,i)=>{
      const rate=ageRate(w,group),countVal=ageCount(w,group);
      const cell=document.createElement("div");
      cell.className="age-heatmap-cell"+(i===visible.length-1?" is-current":"");
      cell.style.background=ageHeatColor(rate,max);
      cell.title=`${w.year}年第${w.week}週 ${group}\n${rate===null?"--":n(rate)} 人/定点\n実数：${countVal===null?"--":n(countVal,0)}人`;
      cell.setAttribute("aria-label",cell.title.replace(/\n/g,"、"));
      row.appendChild(cell);
    });
    host.appendChild(row);
  });

  const w=allWeeks[ageHeatmapEndIndex];
  const period=document.querySelector("#age-heatmap-period");if(period)period.textContent=compareHeading(w);
  const first=document.querySelector("#age-first-week");if(first)first.textContent=ageWeekShort(visible[0]);
  const last=document.querySelector("#age-last-week");if(last)last.textContent=ageWeekShort(visible.at(-1));

  requestAnimationFrame(()=>{
    const sc=document.querySelector("#age-heatmap-scroll");
    if(sc) sc.scrollLeft=sc.scrollWidth;
  });
}
function setAgeHeatmapIndex(index,{stopPlayback=true}={}){
  const slider=document.querySelector("#age-week-slider");
  if(!slider||!allWeeks.length) return;
  const min=Number(slider.min||0), max=Number(slider.max||allWeeks.length-1);
  const next=Math.max(min,Math.min(max,index));
  slider.value=String(next);
  if(stopPlayback) stopAgeHeatmapPlayback();
  renderAgeHeatmap(next);
}
function applyAgeHeatmapRange(range){
  const slider=document.querySelector("#age-week-slider");
  if(!slider||!allWeeks.length) return;
  ageHeatmapRange=Math.min(Number(range)||13,allWeeks.length);
  slider.min=String(Math.max(0,ageHeatmapRange-1));
  slider.max=String(allWeeks.length-1);
  slider.value=String(allWeeks.length-1);
  document.querySelectorAll(".age-range-button").forEach(btn=>{
    const active=Number(btn.dataset.ageRange)===Number(range);
    btn.classList.toggle("is-active",active);
    btn.setAttribute("aria-pressed",active?"true":"false");
  });
  renderAgeHeatmap(allWeeks.length-1);
}
function wireAgeHeatmap(){
  const slider=document.querySelector("#age-week-slider"), play=document.querySelector("#age-play"), prev=document.querySelector("#age-prev-week"), next=document.querySelector("#age-next-week"), latest=document.querySelector("#age-latest");
  if(!slider||!play||!prev||!next||!latest) return;
  applyAgeHeatmapRange(13);
  slider.addEventListener("input",()=>setAgeHeatmapIndex(Number(slider.value)));
  prev.addEventListener("click",()=>setAgeHeatmapIndex(Number(slider.value)-1));
  next.addEventListener("click",()=>setAgeHeatmapIndex(Number(slider.value)+1));
  latest.addEventListener("click",()=>setAgeHeatmapIndex(allWeeks.length-1));
  document.querySelectorAll(".age-range-button").forEach(btn=>btn.addEventListener("click",()=>{stopAgeHeatmapPlayback();applyAgeHeatmapRange(btn.dataset.ageRange);}));
  play.addEventListener("click",()=>{
    if(ageHeatmapTimer){stopAgeHeatmapPlayback();return;}
    let i=Number(slider.value);
    if(i>=allWeeks.length-1){i=Number(slider.min||0);setAgeHeatmapIndex(i,{stopPlayback:false});}
    play.textContent="Ⅱ 一時停止";
    ageHeatmapTimer=setInterval(()=>{
      i=Number(slider.value)+1;
      if(i>=allWeeks.length){setAgeHeatmapIndex(allWeeks.length-1,{stopPlayback:false});stopAgeHeatmapPlayback();return;}
      setAgeHeatmapIndex(i,{stopPlayback:false});
    },650);
  });
}
function renderAgeLatestValueTable(values, colors){
  const host=document.querySelector("#age-latest-values");
  if(!host) return;

  const ageHeader=AGE_GROUPS.map((group,i)=>`<div class="age-latest-cell age-latest-age" style="--age-color:${colors[i]}">${group}</div>`).join("");
  const rateRow=AGE_GROUPS.map((group,i)=>`<div class="age-latest-cell age-latest-value age-latest-rate" style="--age-color:${colors[i]}">${values[i]===null?"--":n(values[i])}</div>`).join("");

  host.innerHTML=`
    <div class="age-latest-table">
      <div class="age-latest-table-row age-latest-table-head">
        <div class="age-latest-row-label age-latest-head-label">年齢</div>
        ${ageHeader}
      </div>
      <div class="age-latest-table-row">
        <div class="age-latest-row-label">人/定点</div>
        ${rateRow}
      </div>
    </div>`;
}

const ageLatestBarLabelsPlugin={
  id:"ageLatestBarLabels",
  afterDatasetsDraw(chart){
    const ctx=chart.ctx;
    const meta=chart.getDatasetMeta(0);
    const data=chart.data.datasets[0]?.data||[];

    ctx.save();
    ctx.textAlign="center";
    ctx.textBaseline="bottom";
    ctx.font='800 12px system-ui,-apple-system,"Segoe UI",sans-serif';
    ctx.fillStyle="#173f63";

    meta.data.forEach((el,i)=>{
      const v=data[i];
      if(v===null||v===undefined||!Number.isFinite(Number(v))) return;
      ctx.fillText(`${n(Number(v),0)}人`,el.x,Math.max(16,el.y-8));
    });

    ctx.restore();
  }
};

function renderAgeLatest(){
  const canvas=document.querySelector("#age-latest-chart");
  if(!canvas||typeof Chart==="undefined"||!allWeeks.length) return;

  ageLatestWeekIndex=allWeeks.length-1;
  const week=allWeeks[ageLatestWeekIndex];
  const values=AGE_GROUPS.map(g=>ageRate(week,g));
  const counts=AGE_GROUPS.map(g=>ageCount(week,g));
  const colors=AGE_GROUPS.map(g=>AGE_COLORS[g]);

  if(ageLatestChart) ageLatestChart.destroy();

  ageLatestChart=new Chart(canvas,{
    type:"bar",
    plugins:[ageLatestBarLabelsPlugin],
    data:{
      labels:AGE_GROUPS,
      datasets:[
        {
          label:"報告数（人）",
          data:counts,
          backgroundColor:colors,
          borderColor:colors,
          borderWidth:1,
          borderRadius:7,
          borderSkipped:false,
          maxBarThickness:86
        }
      ]
    },
    options:{
      responsive:true,
      maintainAspectRatio:false,
      animation:false,
      interaction:{mode:"index",intersect:false},
      plugins:{
        legend:{display:false},
        tooltip:{
          callbacks:{
            title:items=>items?.[0]?.label||"",
            label:c=>{
              const i=c.dataIndex;
              const count=counts[i]===null?"--":`${n(counts[i],0)}人`;
              const rate=values[i]===null?"--":`${n(values[i])} 人/定点`;
              return [` 報告数：${count}`,` 人/定点：${rate}`];
            }
          }
        }
      },
      layout:{padding:{top:24}},
      scales:{
        x:{
          grid:{display:false},
          ticks:{font:{weight:"700"}}
        },
        y:{
          beginAtZero:true,
          grace:"18%",
          grid:{color:"rgba(90,130,150,.10)"},
          title:{display:true,text:"報告数（人）",font:{weight:"700"}},
          ticks:{precision:0}
        }
      }
    }
  });

  const period=document.querySelector("#age-latest-period");
  if(period) period.textContent=compareHeading(week);

  renderAgeLatestValueTable(values, colors);
}

function renderAgeSeriesToggles(){
  const host=document.querySelector("#age-series-toggles");if(!host)return;
  host.innerHTML="";
  AGE_GROUPS.forEach(group=>{
    const b=document.createElement("button");b.type="button";b.className="age-toggle";b.textContent=group;b.style.setProperty("--age-color",AGE_COLORS[group]);
    b.setAttribute("aria-pressed","true");
    b.addEventListener("click",()=>{
      if(ageSeriesVisible.has(group)){ageSeriesVisible.delete(group);b.classList.add("is-off");b.setAttribute("aria-pressed","false");}
      else{ageSeriesVisible.add(group);b.classList.remove("is-off");b.setAttribute("aria-pressed","true");}
      renderAgeSeries(ageSeriesWeeks);
    });
    host.appendChild(b);
  });
}
function renderAgeSeries(weeksCount=13){
  const canvas=document.querySelector("#age-series-chart");if(!canvas||typeof Chart==="undefined")return;
  ageSeriesWeeks=Number(weeksCount)||13;
  const visible=allWeeks.slice(-Math.min(ageSeriesWeeks,allWeeks.length));
  const labels=visible.map(w=>w.label);
  const datasets=AGE_GROUPS.filter(g=>ageSeriesVisible.has(g)).map(group=>({
    label:group,data:visible.map(w=>ageRate(w,group)),borderColor:AGE_COLORS[group],backgroundColor:"transparent",pointRadius:ageSeriesWeeks<=26?2.4:1.4,pointHoverRadius:5,borderWidth:2.1,tension:.22,spanGaps:true
  }));
  if(ageSeriesChart) ageSeriesChart.destroy();
  ageSeriesChart=new Chart(canvas,{
    type:"line",data:{labels,datasets},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>` ${c.dataset.label}：${n(c.raw)} 人/定点`}}},scales:{x:{grid:{display:false},ticks:{maxRotation:0,autoSkip:true,maxTicksLimit:ageSeriesWeeks<=13?13:16,font:{size:10}}},y:{beginAtZero:true,grid:{color:"rgba(90,130,150,.10)"},title:{display:true,text:"人/定点"}}}}
  });
  const inner=document.querySelector(".age-series-inner");
  if(inner) inner.style.minWidth=ageSeriesWeeks<=26?"100%":ageSeriesWeeks<=52?"1150px":"1700px";
  requestAnimationFrame(()=>{const sc=document.querySelector("#age-series-scroll");if(sc)sc.scrollLeft=sc.scrollWidth;});
}
function wireAgeSeriesRange(){
  document.querySelectorAll(".age-series-range-button").forEach(btn=>btn.addEventListener("click",()=>{
    document.querySelectorAll(".age-series-range-button").forEach(b=>b.classList.remove("active"));
    btn.classList.add("active");renderAgeSeries(Number(btn.dataset.ageSeriesWeeks));
  }));
}
function initAgeStatistics(){
  const hasAge=allWeeks.some(w=>w.age_per_sentinel&&Object.keys(w.age_per_sentinel).length);
  const section=document.querySelector("#age-stats");
  if(!section) return;
  if(!hasAge){section.hidden=true;return;}
  ageHeatmapEndIndex=allWeeks.length-1;
  renderAgeLatest();
  renderAgeSeriesToggles();
  renderAgeSeries(13);
  wireAgeSeriesRange();
  wireAgeHeatmap();
}

function formatPeriodWestern(label, year){
  if(!label) return "";
  const y = Number(year);
  // 例: R8/8/31–9/6 → 2026/8/31–9/6
  if(Number.isFinite(y) && /^R\d+\//.test(label)){
    return label.replace(/^R\d+\//, `${y}/`);
  }
  return label;
}

async function main(){
 const res=await fetch(DATA_URL,{cache:"no-store"}); if(!res.ok)throw new Error("influenza_history.json を読み込めません");
 const data=await res.json(); allWeeks=(data.weeks||[]).slice().sort((a,b)=>(a.year-b.year)||(a.week-b.week)); if(!allWeeks.length)throw new Error("週データがありません");
 const updatedEl=document.querySelector("#data-updated-at"); if(updatedEl)updatedEl.textContent=formatUpdatedAt(data.meta?.updated_at);
 latestWeek=allWeeks.at(-1); const prev=allWeeks.at(-2),prev2=allWeeks.at(-3);
 document.querySelector("#latest-period").textContent=formatPeriodWestern(latestWeek.label,latestWeek.year); document.querySelector("#map-period").textContent=latestWeek.label;
 document.querySelector("#latest-value").textContent=n(latestWeek.prefecture); document.querySelector("#prev-value").textContent=n(prev?.prefecture);
 const sentinelValue=n(latestWeek.prefecture);
 const sentinelCurrent=document.querySelector("#sentinel-current-value");
 const sentinelInline=document.querySelector("#sentinel-current-value-inline");
 if(sentinelCurrent) sentinelCurrent.textContent=sentinelValue;
 if(sentinelInline) sentinelInline.textContent=sentinelValue;
 const weekDiff=(prev?.prefecture===null||prev?.prefecture===undefined)?null:absoluteWeekDiff(latestWeek.prefecture,prev.prefecture);
 const wowValueEl=document.querySelector("#wow-value");
 if(wowValueEl){
  wowValueEl.textContent=weekDiff===null?"--":`${weekDiff>=0?"+":"−"}${n(Math.abs(weekDiff))}`;
  const labelEl=wowValueEl.previousElementSibling;
  if(labelEl) labelEl.textContent="前週から";
 }
 document.querySelector("#level-badge").textContent=level(latestWeek.prefecture)[0];
 const tier=tierKey(latestWeek.prefecture);
 const badge=document.querySelector("#level-badge");
 badge.classList.remove("tier-blue","tier-yellow","tier-red","tier-purple");
 badge.classList.add(`tier-${tier}`);
 const big=document.querySelector("#latest-value");
 big.classList.remove("tier-blue","tier-yellow","tier-red","tier-purple");
 big.classList.add(`tier-${tier}`);
 highlightSignal(latestWeek.prefecture); updateHeroSignal(latestWeek.prefecture); await renderWeeklyInsight(latestWeek);
 const geo=await fetchGeoData();
 buildHeroSilhouette(geo);
 buildTrendSilhouette(geo);
 renderTrend(13); wireRangeButtons(); wireTrendRegionControls(); wireGraphCopyButtons(); renderComparison(allWeeks,latestWeek); renderRanking(latestWeek); renderMap(latestWeek,geo); wireMapTimeline(); renderRegionDefinitions(); wireRegionDialog(); initAgeStatistics();
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

   weeklyAIData=ai;
   weeklyAIAudience="general";
   renderWeeklyInsightAudience();
   wireAIAudienceSwitch();

   if(source) source.textContent="AI自動生成";
   if(note){
     note.textContent=ai.disclaimer||"新潟県公表データをもとにAIが自動生成した分析コメントです。";
     note.hidden=false;
   }
 }catch(err){
   weeklyAIData=null;
   box.textContent=cleanTopic(latest.topic);
   if(source) source.textContent="新潟県週報";
   if(note) note.hidden=true;
   document.querySelectorAll(".ai-audience-button").forEach(btn=>btn.disabled=true);
 }
}

function aiEmphasisItems(ai,audience,field,text){
 const source=Array.isArray(ai?.emphasis)?ai.emphasis:[];
 const explicit=source.filter(item=>
   item && item.audience===audience && item.field===field &&
   (item.style==="marker"||item.style==="underline") &&
   typeof item.text==="string" && item.text && text.includes(item.text)
 );
 if(explicit.length) return explicit;
 return deriveAIEmphasis(field,text,audience);
}

function firstMatchText(text,regex){
 const m=text.match(regex);
 return m?m[0]:null;
}

function firstSentenceContaining(text,needles){
 const sentences=text.match(/[^。！？]+[。！？]?/g)||[];
 for(const sentence of sentences){
   if(needles.some(word=>sentence.includes(word))) return sentence.replace(/[。！？]$/,'').trim();
 }
 return null;
}

function deriveAIEmphasis(field,text,audience){
 const items=[];
 const add=(style,value)=>{
   if(value && text.includes(value) && !items.some(x=>x.text===value)) items.push({style,text:value});
 };
 if(!text) return items;

 if(audience==="general"){
   if(field==="headline"){
     add("marker",firstMatchText(text,/\d+週(?:間)?連続で(?:増加|減少)|(?:増加|減少)が続[^、。]*/));
   }else if(field==="summary"){
     add("marker",firstMatchText(text,/\d+(?:\.\d+)?\s*人\/定点/));
     add("marker",firstMatchText(text,/前週から\d+(?:\.\d+)?\s*人\/定点(?:増加|減少)/));
     add("underline",firstSentenceContaining(text,["流行期入りの目安","注意報基準相当","警報基準相当"]));
   }else if(field==="trend"){
     add("marker",firstMatchText(text,/\d+週(?:間)?連続で(?:増加|減少)/));
     add("underline",firstSentenceContaining(text,["注意報基準相当","警報基準相当","近づいて","上回って"]));
   }else if(field==="regional"){
     add("marker",firstMatchText(text,/[^、。]{1,10}?が\d+(?:\.\d+)?\s*人\/定点(?:で最も多く|で最も高く|)/));
   }else if(field==="age_group"){
     add("marker",firstMatchText(text,/\d+～?\d*歳が\d+(?:\.\d+)?\s*人\/定点(?:で最も多く|で最も高く|)/));
   }else if(field==="year_on_year"){
     add("marker",firstMatchText(text,/今年は\d+(?:\.\d+)?\s*人\/定点/));
     add("underline",firstMatchText(text,/前年同週を\d+(?:\.\d+)?\s*人\/定点(?:上回りました|下回りました)/));
   }
 }else{
   if(field==="headline"){
     add("marker",text.replace(/^\s*[^\p{L}\p{N}]+/u,"").trim());
   }else if(field==="summary"){
     add("marker",firstMatchText(text,/\d+週(?:間)?(?:つづけて|続けて)(?:増えています|減っています|増加しています|減少しています)/));
     add("marker",firstMatchText(text,/平均（?へいきん）?で?\d+(?:\.\d+)?人|平均\d+(?:\.\d+)?人/));
   }else if(field==="trend"){
     add("marker",firstSentenceContaining(text,["はっきり増","はっきり減","増えてき","減ってき"]));
   }else if(field==="regional"){
     add("marker",firstSentenceContaining(text,["多くなっています","多いです"]));
   }else if(field==="age_group"){
     add("marker",firstMatchText(text,/いちばん多いのは[^。]+/));
   }else if(field==="year_on_year"){
     add("underline",firstSentenceContaining(text,["去年より","去年の同じころ"]));
   }
 }
 return items.slice(0,3);
}

function appendAIEmphasizedText(target,text,items){
 target.textContent="";
 if(!text){return;}
 const ranges=[];
 for(const item of items||[]){
   const needle=String(item?.text||"");
   if(!needle) continue;
   const start=text.indexOf(needle);
   if(start<0) continue;
   const end=start+needle.length;
   if(ranges.some(r=>!(end<=r.start||start>=r.end))) continue;
   ranges.push({start,end,style:item.style});
 }
 ranges.sort((a,b)=>a.start-b.start);
 let cursor=0;
 for(const range of ranges){
   if(range.start>cursor) target.appendChild(document.createTextNode(text.slice(cursor,range.start)));
   const span=document.createElement("span");
   span.className=range.style==="underline"?"ai-red-underline":"ai-marker";
   span.textContent=text.slice(range.start,range.end);
   target.appendChild(span);
   cursor=range.end;
 }
 if(cursor<text.length) target.appendChild(document.createTextNode(text.slice(cursor)));
}

function renderWeeklyInsightAudience(){
 const box=document.querySelector("#weekly-topic");
 const note=document.querySelector("#ai-topic-note");
 if(!box||!weeklyAIData) return;
 const ai=weeklyAIData;
 const kids=weeklyAIAudience==="kids";
 const prefix=kids?"kids_":"";
 const fields=[
   ["概況",ai[prefix+"summary"]],
   ["推移",ai[prefix+"trend"]],
   ["地域",ai[prefix+"regional"]],
   ["年代",ai[prefix+"age_group"]],
   ["前年同期",ai[prefix+"year_on_year"]]
 ];
 const headline=ai[prefix+"headline"];
 const audience=kids?"kids":"general";

 box.innerHTML="";
 if(headline){
   const lead=document.createElement("p");
   lead.className="ai-insight-headline";
   appendAIEmphasizedText(lead,headline,aiEmphasisItems(ai,audience,"headline",headline));
   box.appendChild(lead);
 }
 const hasContent=Boolean(headline||fields.some(([,text])=>text));
 if(kids&&!hasContent){
   const p=document.createElement("p");
   p.className="ai-insight-paragraph";
   p.textContent="こども向けコメントは、次回のAI週次更新後から表示できます。";
   box.appendChild(p);
   if(note) note.textContent="一般向けコメントは上の「一般向け」ボタンで確認できます。";
   return;
 }
 fields.forEach(([label,text])=>{
   if(!text) return;
   const p=document.createElement("p");
   p.className="ai-insight-paragraph";
   const tag=document.createElement("span");
   tag.className="ai-insight-label";
   tag.textContent=label;
   const body=document.createElement("span");
   const fieldKey={"概況":"summary","推移":"trend","地域":"regional","年代":"age_group","前年同期":"year_on_year"}[label]||"summary";
   appendAIEmphasizedText(body,text,aiEmphasisItems(ai,audience,fieldKey,text));
   p.append(tag,body);
   box.appendChild(p);
 });
 if(note){
   note.textContent=kids
     ?"新潟県公表データをもとにAIが、こどもにも読みやすい表現で自動生成したコメントです。"
     :(ai.disclaimer||"新潟県公表データをもとにAIが自動生成した分析コメントです。");
 }
}
function wireAIAudienceSwitch(){
 document.querySelectorAll(".ai-audience-button").forEach(btn=>{
   btn.disabled=false;
   btn.addEventListener("click",()=>{
     weeklyAIAudience=btn.dataset.aiAudience==="kids"?"kids":"general";
     document.querySelectorAll(".ai-audience-button").forEach(b=>{
       const active=b.dataset.aiAudience===weeklyAIAudience;
       b.classList.toggle("is-active",active);
       b.setAttribute("aria-pressed",active?"true":"false");
     });
     renderWeeklyInsightAudience();
   });
 });
}

function trendValue(week,region){
 if(region==="prefecture") return week?.prefecture;
 return week?.regions?.[region] ?? null;
}
function trendRegionLabel(region){
 if(region==="prefecture") return "県全体";
 if(region==="新潟市") return "新潟市";
 return REGION_TITLE_SUFFIX.has(region) ? `${region}地域` : region;
}

function renderTrendMobileSVG(visible,datasets){
 const host=document.querySelector("#trend-mobile-chart");
 if(!host) return;
 host.replaceChildren();

 const isMobile=window.matchMedia("(max-width: 820px)").matches;
 if(!isMobile){
   host.hidden=true;
   return;
 }
 host.hidden=false;

 const ns="http://www.w3.org/2000/svg";
 const count=visible.length;
 const width=count<=13?760:count<=26?980:count<=52?1320:1880;
 const height=330;
 const pad={left:46,right:18,top:42,bottom:54};
 const plotW=width-pad.left-pad.right;
 const plotH=height-pad.top-pad.bottom;

 const all=[];
 datasets.forEach(ds=>(ds.data||[]).forEach(v=>{if(v===null||v===undefined||v==="")return;const n=Number(v);if(Number.isFinite(n))all.push(n)}));
 let max=Math.max(10,...all);
 if(max<=10) max=10;
 else if(max<=20) max=20;
 else if(max<=30) max=30;
 else max=Math.ceil(max/10)*10;

 const svg=document.createElementNS(ns,"svg");
 svg.setAttribute("viewBox",`0 0 ${width} ${height}`);
 svg.setAttribute("width",String(width));
 svg.setAttribute("height",String(height));
 svg.setAttribute("role","img");
 svg.setAttribute("aria-label",`${trendRegionLabel(trendRegion)}の推移グラフ`);
 svg.classList.add("trend-mobile-svg");

 const add=(name,attrs={},text="")=>{
   const el=document.createElementNS(ns,name);
   Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,String(v)));
   if(text!=="") el.textContent=text;
   svg.appendChild(el);
   return el;
 };

 add("rect",{x:0,y:0,width,height,rx:14,fill:"#fff"});

 // legend
 if(datasets.length>1){
   let lx=pad.left;
   datasets.forEach(ds=>{
     add("line",{x1:lx,y1:18,x2:lx+18,y2:18,stroke:ds.borderColor||"#0b79b6","stroke-width":3,"stroke-dasharray":ds.borderDash?"7 5":"none"});
     add("text",{x:lx+24,y:22,fill:"#536b79","font-size":11,"font-weight":700},ds.label||"");
     lx+=Math.max(115,(ds.label||"").length*12+48);
   });
 }

 const y=(v)=>pad.top+plotH-(Number(v)/max)*plotH;
 const x=(i)=>count<=1?pad.left+plotW/2:pad.left+(i/(count-1))*plotW;

 for(let i=0;i<=5;i++){
   const val=max*i/5;
   const yy=y(val);
   add("line",{x1:pad.left,y1:yy,x2:width-pad.right,y2:yy,stroke:"rgba(90,130,150,.16)","stroke-width":1});
   add("text",{x:pad.left-8,y:yy+4,"text-anchor":"end",fill:"#6f808b","font-size":10},Number.isInteger(val)?String(val):val.toFixed(1));
 }
 add("line",{x1:pad.left,y1:pad.top,x2:pad.left,y2:pad.top+plotH,stroke:"#cddbe3","stroke-width":1});
 add("line",{x1:pad.left,y1:pad.top+plotH,x2:width-pad.right,y2:pad.top+plotH,stroke:"#cddbe3","stroke-width":1});

 const labelStep=Math.max(1,Math.ceil(count/7));
 visible.forEach((w,i)=>{
   if(i%labelStep!==0 && i!==count-1) return;
   const label=w.label||`${w.year}W${w.week}`;
   add("text",{x:x(i),y:height-22,"text-anchor":"middle",fill:"#6f808b","font-size":10},label);
 });

 datasets.forEach((ds,di)=>{
   const pts=[];
   (ds.data||[]).forEach((v,i)=>{
     if(v===null||v===undefined||v==="") return;
     const num=Number(v);
     if(Number.isFinite(num)) pts.push([x(i),y(num)]);
   });
   if(!pts.length) return;

   if(di===0 && pts.length>1){
     const base=pad.top+plotH;
     const poly=[[pts[0][0],base],...pts,[pts[pts.length-1][0],base]].map(a=>a.join(",")).join(" ");
     add("polygon",{points:poly,fill:"rgba(11,121,182,.08)"});
   }
   const d=pts.map((p,i)=>(i?"L":"M")+p[0]+" "+p[1]).join(" ");
   add("path",{d,fill:"none",stroke:ds.borderColor||"#0b79b6","stroke-width":di===0?3:2.2,"stroke-linejoin":"round","stroke-linecap":"round","stroke-dasharray":ds.borderDash?"7 5":"none"});
   pts.forEach(([px,py])=>add("circle",{cx:px,cy:py,r:di===0?3.5:2.6,fill:"#fff",stroke:ds.borderColor||"#0b79b6","stroke-width":2}));
 });

 add("text",{x:14,y:pad.top+plotH/2,fill:"#6f808b","font-size":10,"text-anchor":"middle",transform:`rotate(-90 14 ${pad.top+plotH/2})`},"定点当たり報告数");
 host.appendChild(svg);

 requestAnimationFrame(()=>{
   const sc=document.querySelector("#chart-scroll");
   if(sc) sc.scrollLeft=sc.scrollWidth;
 });
}

function renderTrend(weeksCount=trendWeeks){
 trendWeeks=Number(weeksCount)||13;
 const visible=allWeeks.slice(-Math.min(trendWeeks,allWeeks.length));
 const labels=visible.map(w=>w.label);
 const values=visible.map(w=>trendValue(w,trendRegion));
 const selectedLabel=trendRegionLabel(trendRegion);

 const title=document.querySelector("#trend-title");
 if(title){
   title.replaceChildren();
   const main=document.createElement("span");
   main.className="trend-title-main";
   main.textContent=trendRegion==="prefecture" ? "県全体の推移" : `${selectedLabel}の推移`;
   title.appendChild(main);

   if(trendRegion!=="prefecture"){
     const municipalities=REGION_MUNICIPALITIES[trendRegion]||[];
     if(municipalities.length){
       const sub=document.createElement("span");
       sub.className="trend-title-municipalities";
       sub.textContent=`（${municipalities.join("・")}）`;
       title.appendChild(sub);
     }
   }
 }

 const compare=document.querySelector("#trend-compare-prefecture");
 if(compare){
   compare.disabled=trendRegion==="prefecture";
   compare.checked=trendRegion==="prefecture"?false:trendComparePrefecture;
 }
 const compareWrap=document.querySelector(".trend-compare-toggle");
 if(compareWrap) compareWrap.classList.toggle("is-disabled",trendRegion==="prefecture");

 const showPreviousYear=[13,26,52].includes(trendWeeks);
 const previousValues=showPreviousYear
   ? visible.map(w=>{
       const prev=allWeeks.find(x=>x.year===w.year-1&&x.week===w.week);
       return prev ? trendValue(prev,trendRegion) : null;
     })
   : [];

 if(trendChart) trendChart.destroy();

 const datasets=[{
   label:trendRegion==="prefecture"?`県全体（${latestWeek.year}）`:`${selectedLabel}（${latestWeek.year}）`,
   data:values,
   borderColor:"#0b79b6",
   backgroundColor:"rgba(11,121,182,.10)",
   pointRadius:3,pointHoverRadius:5,borderWidth:2.8,tension:.22,fill:true
 }];

 if(trendRegion!=="prefecture" && trendComparePrefecture){
   datasets.push({
     label:"県計",
     data:visible.map(w=>w.prefecture),
     borderColor:"#5b6f7d",
     backgroundColor:"transparent",
     pointRadius:2.2,pointHoverRadius:4,borderWidth:2.1,tension:.22,fill:false
   });
 }

 if(showPreviousYear){
   datasets.push({
     label:`${trendRegion==="prefecture"?"県全体":selectedLabel}・前年同期`,
     data:previousValues,
     borderColor:"#8fa3b1",
     backgroundColor:"transparent",
     pointRadius:2.2,pointHoverRadius:4,borderWidth:2.1,borderDash:[7,5],
     tension:.22,fill:false,spanGaps:false
   });
 }

 renderTrendMobileSVG(visible,datasets);

 const trendCanvas=document.querySelector("#trend-chart");
 if(!trendCanvas) return;
 const mobileTrend=window.matchMedia("(max-width: 820px)").matches;
 if(mobileTrend){
   if(trendChart){trendChart.destroy();trendChart=null;}
 }else{
 trendChart=new Chart(trendCanvas,{
   type:"line",
   data:{labels,datasets},
   options:{
     responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
     plugins:{
       legend:{display:datasets.length>1,position:"top",align:"end",labels:{usePointStyle:true,boxWidth:8,boxHeight:8,padding:16,font:{size:11,weight:"700"}}},
       tooltip:{callbacks:{label:c=>` ${c.dataset.label}：定点当たり ${n(c.raw)}`}}
     },
     scales:{
       x:{grid:{display:false},ticks:{maxRotation:0,autoSkip:true,maxTicksLimit:trendWeeks<=13?13:trendWeeks<=26?13:16,font:{size:10}}},
       y:{beginAtZero:true,grid:{color:"rgba(90,130,150,.12)"},title:{display:true,text:"定点当たり報告数"}}
     }
   }
 });
 }
 const inner=document.querySelector(".chart-inner");
 if(inner) inner.style.minWidth=trendWeeks<=26?"100%":trendWeeks<=52?"1250px":"1800px";

 // Smartphone browsers can calculate the responsive canvas before the
 // flex/stacked layout has settled. Resize once immediately and once after
 // layout completion so the chart never remains at 0px height/width.
 const resizeTrendChart=()=>{
   if(!trendChart) return;
   const host=trendCanvas.parentElement;
   if(window.matchMedia("(max-width: 820px)").matches && host){
     if(host.getBoundingClientRect().height < 240) host.style.height="330px";
   }
   trendChart.resize();
 };
 requestAnimationFrame(()=>{
   resizeTrendChart();
   const sc=document.querySelector("#chart-scroll");
   if(sc) sc.scrollLeft=sc.scrollWidth;
   setTimeout(resizeTrendChart,120);
 });
}
function wireRangeButtons(){
 document.querySelectorAll(".range-button").forEach(btn=>btn.addEventListener("click",()=>{
   document.querySelectorAll(".range-button").forEach(b=>b.classList.remove("active"));
   btn.classList.add("active");
   renderTrend(Number(btn.dataset.weeks));
 }));
 const latest=document.querySelector("#to-latest");
 if(latest) latest.addEventListener("click",()=>{const sc=document.querySelector("#chart-scroll");if(sc)sc.scrollTo({left:sc.scrollWidth,behavior:"smooth"})});
}
function wireTrendRegionControls(){
 const select=document.querySelector("#trend-region-select");
 const compare=document.querySelector("#trend-compare-prefecture");
 if(select){
   select.value=trendRegion;
   select.addEventListener("change",()=>{
     trendRegion=select.value||"prefecture";
     renderTrend(trendWeeks);
   });
 }
 if(compare){
   compare.addEventListener("change",()=>{
     trendComparePrefecture=compare.checked;
     renderTrend(trendWeeks);
   });
 }
}
async function canvasToBlob(canvas){
 return await new Promise((resolve,reject)=>{
   canvas.toBlob(blob=>blob?resolve(blob):reject(new Error("PNG変換に失敗しました")),"image/png");
 });
}
function downloadBlob(blob,filename){
 const url=URL.createObjectURL(blob);
 const a=document.createElement("a");
 a.href=url;a.download=filename;
 document.body.appendChild(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}

function flattenLeafletTransformsForCapture(mapEl){
 const targets=[...mapEl.querySelectorAll(".leaflet-map-pane, .leaflet-zoom-animated")];
 const saved=[];

 const matrixFromTransform=(value)=>{
   if(!value||value==="none") return null;
   try{
     if(window.DOMMatrixReadOnly) return new DOMMatrixReadOnly(value);
     if(window.WebKitCSSMatrix) return new WebKitCSSMatrix(value);
   }catch(_){}
   const m=value.match(/^matrix\(([^)]+)\)$/);
   if(m){
     const v=m[1].split(",").map(Number);
     if(v.length===6) return {a:v[0],b:v[1],c:v[2],d:v[3],e:v[4],f:v[5]};
   }
   const m3=value.match(/^matrix3d\(([^)]+)\)$/);
   if(m3){
     const v=m3[1].split(",").map(Number);
     if(v.length===16) return {a:v[0],b:v[1],c:v[4],d:v[5],e:v[12],f:v[13]};
   }
   return null;
 };

 targets.forEach(el=>{
   const cs=getComputedStyle(el);
   const m=matrixFromTransform(cs.transform);
   if(!m) return;

   // Leafletの安定時は基本的に平行移動のみ。拡大縮小中は触らない。
   const pureTranslate=
     Math.abs(Number(m.a)-1)<0.001 &&
     Math.abs(Number(m.d)-1)<0.001 &&
     Math.abs(Number(m.b))<0.001 &&
     Math.abs(Number(m.c))<0.001;
   if(!pureTranslate) return;

   saved.push({
     el,
     style:el.getAttribute("style")
   });

   const left=Number.parseFloat(cs.left);
   const top=Number.parseFloat(cs.top);
   el.style.transform="none";
   el.style.left=`${(Number.isFinite(left)?left:0)+Number(m.e||0)}px`;
   el.style.top=`${(Number.isFinite(top)?top:0)+Number(m.f||0)}px`;
 });

 return ()=>{
   saved.forEach(({el,style})=>{
     if(style===null) el.removeAttribute("style");
     else el.setAttribute("style",style);
   });
 };
}

function freezeCanvasRenderingForCapture(root){
 const saved=[];
 root.querySelectorAll("canvas").forEach(canvas=>{
   try{
     const rect=canvas.getBoundingClientRect();
     if(!rect.width||!rect.height) return;

     const img=document.createElement("img");
     img.src=canvas.toDataURL("image/png");
     img.alt="";
     img.setAttribute("aria-hidden","true");
     img.style.display="block";
     img.style.width=`${Math.ceil(rect.width)}px`;
     img.style.height=`${Math.ceil(rect.height)}px`;
     img.style.maxWidth="100%";
     img.style.objectFit="fill";

     const oldDisplay=canvas.style.display;
     canvas.parentNode.insertBefore(img,canvas);
     canvas.style.display="none";
     saved.push({canvas,img,oldDisplay});
   }catch(err){
     console.warn("canvas freeze skipped",err);
   }
 });

 return ()=>{
   saved.forEach(({canvas,img,oldDisplay})=>{
     try{ img.remove(); }catch(_){}
     canvas.style.display=oldDisplay;
   });
 };
}

async function captureGraphRoot(root,{isAgeCard=false}={}){
 const visibleWidth=Math.ceil(root.getBoundingClientRect().width)||root.offsetWidth;
 const width=isAgeCard?visibleWidth:Math.max(root.scrollWidth,root.offsetWidth);
 const options={
   backgroundColor:"#ffffff",
   scale:isAgeCard?1.5:Math.min(2,window.devicePixelRatio||1.5),
   useCORS:true,
   allowTaint:false,
   logging:false,
   width,
   windowWidth:Math.max(document.documentElement.clientWidth,width),
   scrollX:0,
   scrollY:-window.scrollY
 };

 try{
   return await html2canvas(root,options);
 }catch(firstError){
   // 高解像度で失敗するブラウザ向けに、カード全体の体裁を保ったまま
   // 低解像度で1回だけ再試行する。canvas単体コピーには切り替えない。
   console.warn("graph capture retry",firstError);
   await new Promise(r=>setTimeout(r,60));
   return await html2canvas(root,{...options,scale:1});
 }
}


function roundedRectPath(ctx,x,y,w,h,r){
 const rr=Math.max(0,Math.min(r,Math.min(w,h)/2));
 ctx.beginPath();
 ctx.moveTo(x+rr,y);
 ctx.arcTo(x+w,y,x+w,y+h,rr);
 ctx.arcTo(x+w,y+h,x,y+h,rr);
 ctx.arcTo(x,y+h,x,y,rr);
 ctx.arcTo(x,y,x+w,y,rr);
 ctx.closePath();
}

function buildAgeLatestExportCanvas(){
 const source=document.querySelector("#age-latest-chart");
 const week=allWeeks[ageLatestWeekIndex]||latestWeek||allWeeks.at(-1);
 if(!source||!week) throw new Error("年代別グラフを取得できません");

 // 年代別の最新週グラフだけは html2canvas に頼らず、
 // Chart.js の描画結果と見出し・数値表・出典を1枚に直接合成する。
 // これによりブラウザ差で「グラフだけ」「黒背景」「コピー失敗」になるのを防ぐ。
 const W=1200,H=790,dpr=1.5;
 const out=document.createElement("canvas");
 out.width=Math.round(W*dpr);
 out.height=Math.round(H*dpr);
 const ctx=out.getContext("2d");
 ctx.scale(dpr,dpr);

 ctx.fillStyle="#ffffff";
 ctx.fillRect(0,0,W,H);
 roundedRectPath(ctx,1,1,W-2,H-2,28);
 ctx.strokeStyle="#d8e7ef";
 ctx.lineWidth=2;
 ctx.stroke();

 const font='system-ui,-apple-system,"Segoe UI","Yu Gothic UI","Hiragino Kaku Gothic ProN",sans-serif';
 ctx.textBaseline="alphabetic";

 ctx.fillStyle="#536b7a";
 ctx.font=`800 15px ${font}`;
 ctx.letterSpacing="2px";
 ctx.fillText("LATEST WEEK",48,55);
 ctx.letterSpacing="0px";

 ctx.fillStyle="#092f4f";
 ctx.font=`800 30px ${font}`;
 ctx.fillText("最新週の年代別比較",48,96);

 const period=compareHeading(week);
 ctx.font=`700 16px ${font}`;
 const pW=Math.ceil(ctx.measureText(period).width)+32;
 roundedRectPath(ctx,W-48-pW,48,pW,42,21);
 ctx.fillStyle="#eef7fb"; ctx.fill();
 ctx.fillStyle="#2b6686";
 ctx.textAlign="center";
 ctx.fillText(period,W-48-pW/2,75);
 ctx.textAlign="left";

 // Chart.js のCanvasを白背景の上へ描画。
 const chartX=48, chartY=130, chartW=W-96, chartH=390;
 ctx.save();
 roundedRectPath(ctx,chartX,chartY,chartW,chartH,16);
 ctx.clip();
 ctx.fillStyle="#ffffff"; ctx.fillRect(chartX,chartY,chartW,chartH);
 ctx.drawImage(source,0,0,source.width,source.height,chartX,chartY,chartW,chartH);
 ctx.restore();

 // 数値表
 const values=AGE_GROUPS.map(g=>ageRate(week,g));
 const left=48, top=548, labelW=105, cellW=(W-96-labelW)/AGE_GROUPS.length;
 const rowH=48;
 roundedRectPath(ctx,left,top,W-96,rowH*2,10);
 ctx.fillStyle="#f8fbfd"; ctx.fill();
 ctx.strokeStyle="#dce9f0"; ctx.lineWidth=1; ctx.stroke();
 ctx.font=`700 15px ${font}`;
 ctx.textAlign="center"; ctx.textBaseline="middle";
 ctx.fillStyle="#4d6878";
 ctx.fillText("年齢",left+labelW/2,top+rowH/2);
 ctx.fillText("人/定点",left+labelW/2,top+rowH+rowH/2);
 AGE_GROUPS.forEach((g,i)=>{
   const x=left+labelW+i*cellW;
   if(i>0){ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,top+rowH*2);ctx.stroke();}
   ctx.fillStyle="#234a64";
   ctx.font=`700 14px ${font}`;
   ctx.fillText(g,x+cellW/2,top+rowH/2);
   ctx.fillStyle="#0c6596";
   ctx.font=`800 16px ${font}`;
   ctx.fillText(values[i]===null?"--":n(values[i]),x+cellW/2,top+rowH+rowH/2);
 });
 ctx.beginPath();ctx.moveTo(left,top+rowH);ctx.lineTo(W-48,top+rowH);ctx.stroke();

 ctx.textAlign="left"; ctx.textBaseline="alphabetic";
 ctx.fillStyle="#6b7f8d";
 ctx.font=`600 14px ${font}`;
 ctx.fillText("棒グラフは報告数（人）。棒の上に人数を表示し、下の表で各年代の人/定点を確認できます。",48,682);

 ctx.beginPath();ctx.moveTo(48,710);ctx.lineTo(W-48,710);
 ctx.strokeStyle="#e6eef3";ctx.stroke();
 ctx.fillStyle="#71838f";
 ctx.font=`500 13px ${font}`;
 ctx.fillText('出典：新潟県「感染症情報（週報）」',48,742);

 return out;
}

let activeCopyRoot=null;
let activeCopyButton=null;
let activeCopyBlob=null;
let activeCopyBlobToken=0;

function copyTargetTitle(root){
 const title=root?.querySelector("h2,h3")?.textContent?.trim();
 return title||"新潟インフルエンザレーダー";
}
function copyTargetFilename(root){
 return `${copyTargetTitle(root).replace(/[\\/:*?"<>|]/g,"-")}.png`;
}
function copyTargetUrl(root){
 const base=document.querySelector('link[rel="canonical"]')?.href||location.href.split("#")[0];
 const url=new URL(base,location.href);
 if(root?.id) url.hash=root.id;
 return url.href;
}
async function copyTextRobust(text){
 if(navigator.clipboard?.writeText && window.isSecureContext){
   await navigator.clipboard.writeText(text);
   return;
 }
 const textarea=document.createElement("textarea");
 textarea.value=text;
 textarea.setAttribute("readonly","");
 textarea.style.position="fixed";
 textarea.style.left="-9999px";
 textarea.style.top="0";
 document.body.appendChild(textarea);
 textarea.focus();
 textarea.select();
 const ok=document.execCommand("copy");
 textarea.remove();
 if(!ok) throw new Error("テキストコピーに失敗しました");
}
function tabular(rows){
 return rows.map(row=>row.map(v=>String(v??"").replace(/\t/g," ").replace(/\r?\n/g," ")).join("\t")).join("\n");
}
function copyDataForRoot(root){
 const id=root?.id||"";
 const week=currentMapWeek||latestWeek||allWeeks.at(-1);

 if(id==="area-map"){
   const rows=[["地域","市町村","表示週","人/定点","報告数（人）"]];
   REGION_ORDER.forEach(region=>rows.push([
     displayRegionName(region),
     (REGION_MUNICIPALITIES[region]||[]).join("・"),
     compareHeading(week),
     regionRate(week,region)===null?"--":fixed2(regionRate(week,region)),
     regionCountText(regionActualCount(week,region))
   ]));
   return tabular(rows);
 }

 if(id==="region-report"){
   const index=allWeeks.findIndex(w=>Number(w.year)===Number(week?.year)&&Number(w.week)===Number(week?.week));
   const prev=index>0?allWeeks[index-1]:null;
   const rows=[["地域","最新週","最新 人/定点","最新 報告数（人）","前週 人/定点","前週 報告数（人）","増減 人/定点","増減 報告数（人）"]];
   const push=(name,currRate,currCount,prevRate,prevCount)=>{
     const rateDelta=currRate===null||prevRate===null?null:currRate-prevRate;
     const countDelta=currCount===null||prevCount===null?null:currCount-prevCount;
     rows.push([name,compareHeading(week),currRate===null?"--":fixed2(currRate),regionCountText(currCount),prevRate===null?"--":fixed2(prevRate),regionCountText(prevCount),rateDelta===null?"--":signedFixed2(rateDelta),countDelta===null?"--":regionCountText(countDelta,{signed:true})]);
   };
   push("県計",prefectureRate(week),prefectureActualCount(week),prefectureRate(prev),prefectureActualCount(prev));
   REGION_ORDER.forEach(region=>push(displayRegionName(region),regionRate(week,region),regionActualCount(week,region),regionRate(prev,region),regionActualCount(prev,region)));
   return tabular(rows);
 }

 if(id==="trend"){
   const visible=allWeeks.slice(-Math.min(trendWeeks,allWeeks.length));
   const selectedLabel=trendRegionLabel(trendRegion);
   const rows=[["週",selectedLabel+(trendRegion==="prefecture"?"":" 人/定点")]];
   if(trendRegion!=="prefecture"&&trendComparePrefecture) rows[0].push("県計 人/定点");
   if([13,26,52].includes(trendWeeks)) rows[0].push(`${selectedLabel} 前年同期 人/定点`);
   visible.forEach(w=>{
     const row=[`${w.year}年第${w.week}週 ${w.label||""}`,n(trendValue(w,trendRegion))];
     if(trendRegion!=="prefecture"&&trendComparePrefecture) row.push(n(w.prefecture));
     if([13,26,52].includes(trendWeeks)){
       const prev=allWeeks.find(x=>x.year===w.year-1&&x.week===w.week);
       row.push(prev?n(trendValue(prev,trendRegion)):"--");
     }
     rows.push(row);
   });
   return tabular(rows);
 }

 if(id==="age-latest-card"){
   const w=allWeeks[ageLatestWeekIndex]||latestWeek||allWeeks.at(-1);
   return tabular([["年代","表示週","人/定点","報告数（人）"],...AGE_GROUPS.map(g=>[g,compareHeading(w),ageRate(w,g)===null?"--":n(ageRate(w,g)),ageCount(w,g)===null?"--":n(ageCount(w,g),0)])]);
 }

 if(id==="age-series-card"){
   const groups=AGE_GROUPS.filter(g=>ageSeriesVisible.has(g));
   const visible=allWeeks.slice(-Math.min(ageSeriesWeeks,allWeeks.length));
   return tabular([["週",...groups],...visible.map(w=>[`${w.year}年第${w.week}週 ${w.label||""}`,...groups.map(g=>ageRate(w,g)===null?"--":n(ageRate(w,g)) )])]);
 }

 if(id==="age-heatmap-card"){
   const end=Math.max(0,Math.min(allWeeks.length-1,ageHeatmapEndIndex));
   const count=Math.min(ageHeatmapRange,end+1);
   const visible=allWeeks.slice(Math.max(0,end-count+1),end+1);
   return tabular([["年代 / 週",...visible.map(w=>`${w.year}W${w.week}`)],...AGE_GROUPS.map(g=>[g,...visible.map(w=>ageRate(w,g)===null?"--":n(ageRate(w,g)) )])]);
 }

 const table=root?.querySelector("table");
 if(table){
   return [...table.rows].map(row=>[...row.cells].map(cell=>cell.innerText.trim()).join("\t")).join("\n");
 }
 return `${copyTargetTitle(root)}\n${copyTargetUrl(root)}`;
}


function isIOSLike(){
  const ua=navigator.userAgent||"";
  return /iPad|iPhone|iPod/.test(ua) || (navigator.platform==="MacIntel" && navigator.maxTouchPoints>1);
}

async function buildMobileTrendExportCanvas(){
  const svg=document.querySelector("#trend-mobile-chart svg");
  if(!svg) throw new Error("スマホ用推移グラフを取得できません");

  const vb=svg.viewBox?.baseVal;
  const srcW=vb?.width||Number(svg.getAttribute("width"))||760;
  const srcH=vb?.height||Number(svg.getAttribute("height"))||330;
  const W=1200;
  const chartX=48, chartY=142, chartW=W-96;
  const chartH=Math.round(chartW*(srcH/srcW));
  const H=chartY+chartH+118;
  const dpr=1.35;

  const out=document.createElement("canvas");
  out.width=Math.round(W*dpr);
  out.height=Math.round(H*dpr);
  const ctx=out.getContext("2d");
  ctx.scale(dpr,dpr);
  ctx.fillStyle="#fff";
  ctx.fillRect(0,0,W,H);

  const font='system-ui,-apple-system,"Segoe UI","Yu Gothic UI","Hiragino Kaku Gothic ProN",sans-serif';
  ctx.fillStyle="#536b7a";
  ctx.font=`800 15px ${font}`;
  ctx.fillText("TREND",48,50);

  ctx.fillStyle="#092f4f";
  ctx.font=`800 31px ${font}`;
  ctx.fillText(copyTargetTitle(document.querySelector("#trend")),48,91);

  const rangeLabel=trendWeeks===13?"3か月":trendWeeks===26?"半年":trendWeeks===52?"1年":"2年";
  ctx.fillStyle="#6c8190";
  ctx.font=`700 15px ${font}`;
  ctx.fillText(`表示期間：${rangeLabel}`,48,120);

  const clone=svg.cloneNode(true);
  clone.setAttribute("xmlns","http://www.w3.org/2000/svg");
  clone.setAttribute("width",String(srcW));
  clone.setAttribute("height",String(srcH));
  const source=new XMLSerializer().serializeToString(clone);
  const blob=new Blob([source],{type:"image/svg+xml;charset=utf-8"});
  const url=URL.createObjectURL(blob);

  try{
    const img=await new Promise((resolve,reject)=>{
      const el=new Image();
      el.onload=()=>resolve(el);
      el.onerror=()=>reject(new Error("スマホ用推移グラフのPNG化に失敗しました"));
      el.src=url;
    });
    ctx.drawImage(img,0,0,srcW,srcH,chartX,chartY,chartW,chartH);
  }finally{
    URL.revokeObjectURL(url);
  }

  const footerY=chartY+chartH+52;
  ctx.strokeStyle="#e6eef3";
  ctx.beginPath();ctx.moveTo(48,footerY-22);ctx.lineTo(W-48,footerY-22);ctx.stroke();
  ctx.fillStyle="#71838f";
  ctx.font=`500 13px ${font}`;
  ctx.fillText('出典：新潟県「感染症情報（週報）」',48,footerY);

  return out;
}

async function makeCopyImageBlob(root){
 if(!root) throw new Error("コピー対象が見つかりません");
 if(root.classList.contains("age-latest-card")) return canvasToBlob(buildAgeLatestExportCanvas());
 if(root.id==="trend" && window.matchMedia("(max-width: 820px)").matches){
   return canvasToBlob(await buildMobileTrendExportCanvas());
 }
 if(typeof html2canvas!=="function") throw new Error("画像作成機能を読み込めませんでした");

 const isMap=root.id==="area-map";
 const isAgeCard=Boolean(root.closest("#age-stats"));
 const hidden=[];
 let restoreLeaflet=()=>{};
 let restoreCanvases=()=>{};

 root.querySelectorAll("[data-copy-graph]").forEach(btn=>{
   hidden.push([btn,btn.style.visibility]);
   btn.style.visibility="hidden";
 });
 if(!isMap) root.classList.add("is-graph-exporting");

 try{
   if(isMap&&mapInstance){
     try{mapInstance.stop();}catch(_){}
     try{mapInstance.invalidateSize(false);}catch(_){}
     await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
     await new Promise(r=>setTimeout(r,80));
     const mapEl=root.querySelector("#map");
     if(mapEl) restoreLeaflet=flattenLeafletTransformsForCapture(mapEl);
   }else{
     await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
     if(isAgeCard){
       restoreCanvases=freezeCanvasRenderingForCapture(root);
       await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
     }
   }
   const canvas=await captureGraphRoot(root,{isAgeCard});
   return await canvasToBlob(canvas);
 }finally{
   try{restoreCanvases();}catch(_){}
   try{restoreLeaflet();}catch(_){}
   hidden.forEach(([btn,visibility])=>btn.style.visibility=visibility);
   root.classList.remove("is-graph-exporting");
   if(isMap){try{mapInstance?.invalidateSize(false);}catch(_){}}
 }
}

async function writeImageToClipboard(blob){
 if(!(navigator.clipboard?.write&&window.ClipboardItem&&window.isSecureContext)) return false;
 try{
   await navigator.clipboard.write([new ClipboardItem({"image/png":blob})]);
   return true;
 }catch(err){
   console.warn("clipboard image write failed",err);
   return false;
 }
}
function pngFile(blob,root){
 return new File([blob],copyTargetFilename(root),{type:"image/png",lastModified:Date.now()});
}
async function shareImageOrLink(root,blob=null){
 if(!navigator.share) return false;
 const title=copyTargetTitle(root);
 const text=`新潟インフルエンザレーダー｜${title}`;

 if(blob&&window.File){
   const file=pngFile(blob,root);
   const fileData={title,text,files:[file]};
   try{
     if(!navigator.canShare || navigator.canShare(fileData)){
       await navigator.share(fileData);
       return true;
     }
   }catch(err){
     if(err?.name==="AbortError") return true;
     console.warn("file share failed",err);
   }
 }

 try{
   await navigator.share({title,text,url:copyTargetUrl(root)});
   return true;
 }catch(err){
   if(err?.name!=="AbortError") console.warn("link share failed",err);
   return err?.name==="AbortError";
 }
}

function setCopyDialogStatus(message,isError=false){
 const status=document.querySelector("#copy-dialog-status");
 if(!status) return;
 status.textContent=message;
 status.classList.toggle("is-error",Boolean(isError));
}
function setCopyDialogBusy(busy){
 document.querySelectorAll("#copy-dialog [data-copy-action]").forEach(btn=>btn.disabled=busy);
}
function setCopyImageActionsReady(ready){
  document.querySelectorAll('#copy-dialog [data-copy-action="image"], #copy-dialog [data-copy-action="download"]').forEach(btn=>{
    btn.disabled=!ready;
  });
}
function configureCopyDialogForDevice(){
  const imageButton=document.querySelector('#copy-dialog [data-copy-action="image"]');
  const shareButton=document.querySelector('#copy-dialog [data-copy-action="share"]');
  if(imageButton){
    const strong=imageButton.querySelector("strong");
    const span=imageButton.querySelector("span");
    if(isIOSLike()){
      if(strong) strong.textContent="画像を共有・保存";
      if(span) span.textContent="iPhoneでは画像コピーの代わりに共有メニューを使用";
    }else{
      if(strong) strong.textContent="画像をコピー";
      if(span) span.textContent="対応端末ではクリップボードへ。非対応時は共有・保存へ切替";
    }
  }
  if(shareButton) shareButton.hidden=!navigator.share;
}

function closeCopyDialog(){
 const dialog=document.querySelector("#copy-dialog");
 if(dialog?.open) dialog.close();
 activeCopyRoot=null;
 activeCopyButton=null;
 activeCopyBlob=null;
 activeCopyBlobToken++;
}
function openCopyDialog(button){
 const root=button.closest("[data-copy-root]");
 if(!root) return;
 activeCopyRoot=root;
 activeCopyButton=button;
 activeCopyBlob=null;
 const token=++activeCopyBlobToken;
 const dialog=document.querySelector("#copy-dialog");
 const target=document.querySelector("#copy-dialog-target");
 if(target) target.textContent=copyTargetTitle(root);
 configureCopyDialogForDevice();
 setCopyImageActionsReady(false);
 setCopyDialogStatus("画像を準備しています…");
 if(dialog?.showModal) dialog.showModal();
 else if(dialog) dialog.setAttribute("open","");

 makeCopyImageBlob(root).then(blob=>{
   if(token!==activeCopyBlobToken || root!==activeCopyRoot) return;
   activeCopyBlob=blob;
   setCopyImageActionsReady(true);
   setCopyDialogStatus("");
 }).catch(err=>{
   console.error("copy image preparation failed",err);
   if(token!==activeCopyBlobToken || root!==activeCopyRoot) return;
   activeCopyBlob=null;
   setCopyImageActionsReady(false);
   setCopyDialogStatus("画像の準備に失敗しました。データコピーまたはリンク共有は利用できます。",true);
 });
}

async function runCopyDialogAction(action){
 const root=activeCopyRoot;
 if(!root) return;
 setCopyDialogBusy(true);
 try{
   if(action==="data"){
     setCopyDialogStatus("コピー中…");
     await copyTextRobust(copyDataForRoot(root));
     setCopyDialogStatus("データをコピーしました");
     return;
   }
   if(action==="link"){
     setCopyDialogStatus("コピー中…");
     await copyTextRobust(copyTargetUrl(root));
     setCopyDialogStatus("リンクをコピーしました");
     return;
   }

   if(action==="share"){
     setCopyDialogStatus("共有メニューを開いています…");
     const shared=await shareImageOrLink(root,activeCopyBlob);
     setCopyDialogStatus(shared?"共有メニューを開きました":"この端末では共有機能を利用できません",!shared);
     return;
   }

   const blob=activeCopyBlob;
   if(!blob) throw new Error("画像の準備が完了していません");

   if(action==="download"){
     downloadBlob(blob,copyTargetFilename(root));
     setCopyDialogStatus("PNGを保存しました");
     return;
   }

   if(action==="image"){
     if(isIOSLike()){
       setCopyDialogStatus("共有メニューを開いています…");
       if(await shareImageOrLink(root,blob)){
         setCopyDialogStatus("画像を共有できます");
         return;
       }
       downloadBlob(blob,copyTargetFilename(root));
       setCopyDialogStatus("PNGを保存しました");
       return;
     }

     if(await writeImageToClipboard(blob)){
       setCopyDialogStatus("画像をコピーしました");
       return;
     }
     if(await shareImageOrLink(root,blob)){
       setCopyDialogStatus("画像コピー非対応のため共有メニューを開きました");
       return;
     }
     downloadBlob(blob,copyTargetFilename(root));
     setCopyDialogStatus("画像コピー非対応のためPNGを保存しました");
   }
 }catch(err){
   console.error(err);
   setCopyDialogStatus("処理できませんでした。データコピーまたはリンクコピーは利用できます。",true);
 }finally{
   setCopyDialogBusy(false);
   if(!activeCopyBlob) setCopyImageActionsReady(false);
 }
}

function wireCopyDialog(){
 const dialog=document.querySelector("#copy-dialog");
 if(!dialog||dialog.dataset.wired==="1") return;
 dialog.dataset.wired="1";
 document.querySelector("#copy-dialog-close")?.addEventListener("click",closeCopyDialog);
 dialog.addEventListener("click",e=>{if(e.target===dialog)closeCopyDialog();});
 dialog.addEventListener("cancel",e=>{e.preventDefault();closeCopyDialog();});
 dialog.querySelectorAll("[data-copy-action]").forEach(btn=>btn.addEventListener("click",()=>runCopyDialogAction(btn.dataset.copyAction)));
}
function wireGraphCopyButtons(){
 wireCopyDialog();
 document.querySelectorAll("[data-copy-graph]").forEach(btn=>{
   if(btn.dataset.copyWired==="1") return;
   btn.dataset.copyWired="1";
   btn.addEventListener("click",()=>openCopyDialog(btn));
 });
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
function fixed2(v){
 const x=Number(v);
 return Number.isFinite(x)?x.toFixed(2):"--";
}
function regionRate(week,region){
 const v=week?.regions?.[region];
 return Number.isFinite(Number(v))?Number(v):null;
}
function regionActualCount(week,region){
 const v=week?.region_counts?.[region];
 return Number.isFinite(Number(v))?Number(v):null;
}
function prefectureRate(week){
 const v=week?.prefecture;
 return Number.isFinite(Number(v))?Number(v):null;
}
function prefectureActualCount(week){
 const direct=week?.prefecture_count;
 if(Number.isFinite(Number(direct))) return Number(direct);
 const verified=week?.verification?.prefecture_count;
 if(Number.isFinite(Number(verified))) return Number(verified);
 const counts=REGION_ORDER.map(region=>regionActualCount(week,region));
 if(counts.length && counts.every(v=>v!==null)) return counts.reduce((sum,v)=>sum+Number(v),0);
 return null;
}
function prefectureValueHTML(week){
 if(!week) return '<span class="region-rate">--</span><span class="region-count-wrap">（<span class="region-actual-count">--</span>）</span>';
 const rate=prefectureRate(week);
 if(rate===null) return '<span class="region-rate">--</span><span class="region-count-wrap">（<span class="region-actual-count">--</span>）</span>';
 const count=prefectureActualCount(week);
 return `<span class="region-rate">${fixed2(rate)}</span><span class="region-count-wrap">（<span class="region-actual-count">${regionCountText(count)}</span>）</span>`;
}
function regionCountText(value,{signed=false}={}){
 if(value===null||value===undefined||!Number.isFinite(Number(value))) return "--";
 const n=Math.round(Number(value));
 if(signed && n>0) return `+${n}`;
 return String(n);
}
function regionValueHTML(week,region){
 if(!week) return '<span class="region-rate">--</span><span class="region-count-wrap">（<span class="region-actual-count">--</span>）</span>';
 const rate=regionRate(week,region);
 if(rate===null) return '<span class="region-rate">--</span><span class="region-count-wrap">（<span class="region-actual-count">--</span>）</span>';
 const count=regionActualCount(week,region);
 return `<span class="region-rate">${fixed2(rate)}</span><span class="region-count-wrap">（<span class="region-actual-count">${regionCountText(count)}</span>）</span>`;
}
function signedFixed2(value){
 const v=Number(value);
 if(!Number.isFinite(v)) return "--";
 if(v>0) return `+${v.toFixed(2)}`;
 if(v<0) return `-${Math.abs(v).toFixed(2)}`;
 return "0.00";
}
function formatRegionDelta(current,previous,region){
 const currRate=regionRate(current,region);
 const prevRate=regionRate(previous,region);
 if(currRate===null||prevRate===null){
   return {
     html:'<span class="region-rate">--</span><span class="region-count-wrap">（<span class="region-actual-count">--</span>）</span>',
     className:"delta-flat"
   };
 }
 const rateDiff=currRate-prevRate;
 const currCount=regionActualCount(current,region);
 const prevCount=regionActualCount(previous,region);
 const countDiff=(currCount===null||prevCount===null)?null:currCount-prevCount;
 return {
   html:`<span class="region-rate">${signedFixed2(rateDiff)}</span><span class="region-count-wrap">（<span class="region-actual-count">${regionCountText(countDiff,{signed:true})}</span>）</span>`,
   className:rateDiff>0?"delta-up":rateDiff<0?"delta-down":"delta-flat"
 };
}
function formatPrefectureDelta(current,previous){
 const currRate=prefectureRate(current);
 const prevRate=prefectureRate(previous);
 if(currRate===null||prevRate===null){
   return {
     html:'<span class="region-rate">--</span><span class="region-count-wrap">（<span class="region-actual-count">--</span>）</span>',
     className:"delta-flat"
   };
 }
 const rateDiff=currRate-prevRate;
 const currCount=prefectureActualCount(current);
 const prevCount=prefectureActualCount(previous);
 const countDiff=(currCount===null||prevCount===null)?null:currCount-prevCount;
 return {
   html:`<span class="region-rate">${signedFixed2(rateDiff)}</span><span class="region-count-wrap">（<span class="region-actual-count">${regionCountText(countDiff,{signed:true})}</span>）</span>`,
   className:rateDiff>0?"delta-up":rateDiff<0?"delta-down":"delta-flat"
 };
}
function renderRanking(weekData){
 const box=document.querySelector("#ranking");
 if(!box) return;
 box.innerHTML="";
 const period=document.querySelector("#ranking-period");
 if(period) period.textContent=weekData.label||`${weekData.year} 第${weekData.week}週`;

 const latestIndex=allWeeks.findIndex(w=>Number(w.year)===Number(weekData.year)&&Number(w.week)===Number(weekData.week));
 const latest=weekData;
 const prev=latestIndex>0?allWeeks[latestIndex-1]:null;

 const wrap=document.createElement("div");
 wrap.className="region-week-table-wrap";
 const table=document.createElement("table");
 table.className="region-week-table";
 table.innerHTML=`
   <colgroup>
     <col class="region-col-name">
     <col class="region-col-value">
     <col class="region-col-value">
     <col class="region-col-delta">
   </colgroup>
   <thead>
     <tr>
       <th scope="col">地域</th>
       <th scope="col">最新</th>
       <th scope="col">前週</th>
       <th scope="col">増減</th>
     </tr>
   </thead>`;
 const tbody=document.createElement("tbody");

 // 県計は地域別データの基準値として最上段に固定表示する。
 // 新潟市との境界はCSSで二重線にして、地域行とは視覚的に区切る。
 {
   const latestRate=prefectureRate(latest);
   const tier=latestRate===null?"blue":tierKey(latestRate);
   const tr=document.createElement("tr");
   tr.className=`region-signal-row prefecture-total-row tier-bg-${tier}`;

   const th=document.createElement("th");
   th.scope="row";
   th.innerHTML='<span class="region-signal-dot" aria-hidden="true"></span><span class="region-name-stack"><span class="region-name-main">県計</span></span>';
   tr.appendChild(th);

   const latestTd=document.createElement("td");
   latestTd.className="region-current-value";
   latestTd.innerHTML=prefectureValueHTML(latest);
   tr.appendChild(latestTd);

   const prevTd=document.createElement("td");
   prevTd.innerHTML=prefectureValueHTML(prev);
   tr.appendChild(prevTd);

   const deltaTd=document.createElement("td");
   const delta=formatPrefectureDelta(latest,prev);
   deltaTd.className=`region-delta ${delta.className}`;
   deltaTd.innerHTML=delta.html;
   tr.appendChild(deltaTd);

   tbody.appendChild(tr);
 }

 REGION_ORDER.forEach(region=>{
   const latestRate=regionRate(latest,region);
   const tier=latestRate===null?"blue":tierKey(latestRate);
   const tr=document.createElement("tr");
   tr.className=`region-signal-row tier-bg-${tier}`;

   const th=document.createElement("th");
   th.scope="row";
   const municipalities=(REGION_MUNICIPALITIES[region]||[]).join("・");
   const municipalityLine=region==="新潟市" ? "" : `<span class="region-municipalities">${municipalities}</span>`;
   th.innerHTML=`<span class="region-signal-dot" aria-hidden="true"></span><span class="region-name-stack"><span class="region-name-main">${region}</span>${municipalityLine}</span>`;
   tr.appendChild(th);

   const latestTd=document.createElement("td");
   latestTd.className="region-current-value";
   latestTd.innerHTML=regionValueHTML(latest,region);
   tr.appendChild(latestTd);

   const prevTd=document.createElement("td");
   prevTd.innerHTML=regionValueHTML(prev,region);
   tr.appendChild(prevTd);

   const deltaTd=document.createElement("td");
   const delta=formatRegionDelta(latest,prev,region);
   deltaTd.className=`region-delta ${delta.className}`;
   deltaTd.innerHTML=delta.html;
   tr.appendChild(deltaTd);

   tbody.appendChild(tr);
 });
 table.appendChild(tbody);
 wrap.appendChild(table);
 box.appendChild(wrap);

 const legend=document.createElement("div");
 legend.className="region-week-table-legend";
 legend.innerHTML=`
   <p><strong>数値：</strong>定点当たり報告数（人/定点） <span class="legend-sep">｜</span> <strong>（ ）内：</strong>実数（人） <span class="legend-sep">｜</span> <strong>増減：</strong>最新週 − 前週</p>
   <p class="region-signal-legend"><strong>流行水準：</strong><span><i class="legend-signal legend-blue"></i>1.00未満</span><span><i class="legend-signal legend-yellow"></i>1.00以上10.00未満</span><span><i class="legend-signal legend-red"></i>10.00以上30.00未満</span><span><i class="legend-signal legend-purple"></i>30.00以上</span></p>`;
 box.appendChild(legend);
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
   const bounds=mapGeoLayer.getBounds();
   mapInstance.invalidateSize(false);
   // 全域が必ず収まるよう、上下左右に余白を確保する。
   // fitBounds 後の追加ズームは、村上側・粟島側がわずかに欠ける原因になるため行わない。
   mapInstance.fitBounds(bounds,{
     paddingTopLeft:[28,32],
     paddingBottomRight:[28,28]
   });

   // CSSレイアウト確定後にも再計算し、初回表示時の切れを防ぐ
   setTimeout(()=>{
     try{
       mapInstance.invalidateSize(false);
       mapInstance.fitBounds(bounds,{
         paddingTopLeft:[28,32],
         paddingBottomRight:[28,28]
       });
     }catch(_){}
   },120);
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

 applyMapRange(13);

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
let trendViewportResizeTimer=null;
let trendWasMobile=window.matchMedia("(max-width: 820px)").matches;
function refreshTrendChartForViewport(){
 clearTimeout(trendViewportResizeTimer);
 trendViewportResizeTimer=setTimeout(()=>{
   const nowMobile=window.matchMedia("(max-width: 820px)").matches;
   if(nowMobile!==trendWasMobile){
     trendWasMobile=nowMobile;
     renderTrend(trendWeeks);
     return;
   }
   if(nowMobile){
     renderTrend(trendWeeks);
   }else if(trendChart){
     trendChart.resize();
   }
 },120);
}
window.addEventListener("resize",refreshTrendChartForViewport,{passive:true});
window.addEventListener("orientationchange",()=>{setTimeout(()=>renderTrend(trendWeeks),120);},{passive:true});

main().catch(err=>{console.error(err);document.querySelector("#weekly-topic").textContent="データの読み込みに失敗しました。data/influenza_history.json の配置を確認してください。"});