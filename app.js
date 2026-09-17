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

 box.innerHTML="";
 if(headline){
   const lead=document.createElement("p");
   lead.className="ai-insight-headline";
   lead.textContent=headline;
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
   body.textContent=text;
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
 return region==="prefecture" ? "県全体" : region;
}
function renderTrend(weeksCount=trendWeeks){
 trendWeeks=Number(weeksCount)||13;
 const visible=allWeeks.slice(-Math.min(trendWeeks,allWeeks.length));
 const labels=visible.map(w=>w.label);
 const values=visible.map(w=>trendValue(w,trendRegion));
 const selectedLabel=trendRegionLabel(trendRegion);

 const title=document.querySelector("#trend-title");
 if(title) title.textContent=trendRegion==="prefecture" ? "県全体の推移" : `${selectedLabel}の推移`;

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

 trendChart=new Chart(document.querySelector("#trend-chart"),{
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
 const inner=document.querySelector(".chart-inner");
 if(inner) inner.style.minWidth=trendWeeks<=26?"100%":trendWeeks<=52?"1250px":"1800px";
 requestAnimationFrame(()=>{const sc=document.querySelector("#chart-scroll");if(sc)sc.scrollLeft=sc.scrollWidth;});
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

async function copyGraphCard(button){
 const root=button.closest("[data-copy-root]");
 if(!root) return;

 const isMap=root.id==="area-map";
 const originalText=button.textContent;
 const originalVisibility=button.style.visibility;
 let restoreLeaflet=()=>{};

 button.disabled=true;
 button.textContent="作成中…";

 // 通常グラフは従来どおり「コピー用表示」にする。
 // Leaflet地図だけは、レイアウトを変えると内部座標がずれるため
 // 画面の配置を一切変えずにキャプチャする。
 if(isMap){
   button.style.visibility="hidden";
 }else{
   root.classList.add("is-graph-exporting");
 }

 try{
   if(typeof html2canvas!=="function") throw new Error("画像コピー機能を読み込めませんでした");

   if(isMap && mapInstance){
     // 描画・ズームアニメーションを止め、現在の枠寸法でLeafletを確定。
     try{ mapInstance.stop(); }catch(_){}
     try{ mapInstance.invalidateSize(false); }catch(_){}
     await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
     await new Promise(r=>setTimeout(r,80));

     // html2canvas と Leaflet の translate3d の相性で位置ずれが起こるため、
     // キャプチャ中だけ translate を left/top に焼き込む。
     const mapEl=root.querySelector("#map");
     if(mapEl) restoreLeaflet=flattenLeafletTransformsForCapture(mapEl);
   }else{
     await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
   }

   const width=Math.max(root.scrollWidth,root.offsetWidth);
   const canvas=await html2canvas(root,{
     backgroundColor:"#ffffff",
     scale:Math.min(2,window.devicePixelRatio||1.5),
     useCORS:true,
     logging:false,
     width,
     windowWidth:Math.max(document.documentElement.clientWidth,width),
     scrollX:0,
     scrollY:-window.scrollY
   });

   const blob=await canvasToBlob(canvas);
   let copied=false;

   if(navigator.clipboard && window.ClipboardItem){
     try{
       await navigator.clipboard.write([new ClipboardItem({"image/png":blob})]);
       copied=true;
     }catch(_){}
   }

   if(copied){
     button.textContent="✓ コピーしました";
   }else{
     const title=(root.querySelector("h2,h3")?.textContent||"influenza-graph").replace(/[\\/:*?"<>|]/g,"-");
     downloadBlob(blob,`${title}.png`);
     button.textContent="PNGを保存しました";
   }
 }catch(err){
   console.error(err);
   button.textContent="コピーできませんでした";
 }finally{
   try{ restoreLeaflet(); }catch(_){}
   if(isMap){
     button.style.visibility=originalVisibility;
     try{ mapInstance?.invalidateSize(false); }catch(_){}
   }else{
     root.classList.remove("is-graph-exporting");
   }
   setTimeout(()=>{
     button.disabled=false;
     button.textContent=originalText;
   },1800);
 }
}

function wireGraphCopyButtons(){
 document.querySelectorAll("[data-copy-graph]").forEach(btn=>btn.addEventListener("click",()=>copyGraphCard(btn)));
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
   const bounds=mapGeoLayer.getBounds();
   // GeoJSONの外接範囲そのものではなく、少し広げた範囲を表示する。
   // Leafletの丸めやCSS確定後の再計算で北端・島部が欠けるのを防ぐ。
   const safeBounds=bounds.pad(0.12);

   mapInstance.invalidateSize(false);
   mapInstance.fitBounds(safeBounds,{
     padding:[18,18],
     animate:false
   });

   // CSSレイアウト確定後にも同じ安全域で再計算
   setTimeout(()=>{
     try{
       mapInstance.invalidateSize(false);
       mapInstance.fitBounds(safeBounds,{
         padding:[18,18],
         animate:false
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
main().catch(err=>{console.error(err);document.querySelector("#weekly-topic").textContent="データの読み込みに失敗しました。data/influenza_history.json の配置を確認してください。"});