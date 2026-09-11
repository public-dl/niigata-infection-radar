
const DATA_URL = "./data/influenza_history.json";
const GEOJSON_URL = "https://raw.githubusercontent.com/smartnews-smri/japan-topography/refs/heads/main/data/municipality/geojson/s0010/N03-21_15_210101.json";

const REGION_MUNICIPALITIES = {
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

function n(v, digits=2){
  if(v === null || v === undefined || Number.isNaN(Number(v))) return "--";
  return Number(v).toFixed(digits).replace(/\.00$/,"").replace(/(\.\d)0$/,"$1");
}
function level(v){
  if(v >= 30) return ["警報の目安以上","danger"];
  if(v >= 10) return ["注意報の目安以上","warn"];
  if(v >= 1) return ["流行期","active"];
  return ["流行期前","quiet"];
}
function color(v){
  if(v >= 30) return "#e86b5d";
  if(v >= 10) return "#f0c35e";
  if(v >= 1) return "#8fd0e6";
  return "#e9f3f7";
}
function municipalityName(props){
  return props.N03_004 || props.N03_003 || props.name || props.NAME || "";
}
function regionForMunicipality(name){
  for(const [region, municipalities] of Object.entries(REGION_MUNICIPALITIES)){
    if(municipalities.includes(name)) return region;
  }
  return null;
}
function cleanTopic(t){
  if(!t) return "今週はインフルエンザに関する特記事項は掲載されていません。";
  return t
    .replace(/^インフルエンザ/,"")
    .replace(/（別紙.*?参照）/g,"")
    .replace(/[○〇]/g,"\n○")
    .trim();
}

async function main(){
  const res = await fetch(DATA_URL,{cache:"no-store"});
  if(!res.ok) throw new Error("influenza_history.json を読み込めません");
  const data = await res.json();
  const weeks = (data.weeks || []).slice().sort((a,b)=>(a.year-b.year)||(a.week-b.week));
  if(!weeks.length) throw new Error("週データがありません");

  const latest = weeks.at(-1);
  const prev = weeks.at(-2);
  const prev2 = weeks.at(-3);

  document.querySelector("#latest-period").textContent = latest.label;
  document.querySelector("#map-period").textContent = latest.label;
  document.querySelector("#latest-value").textContent = n(latest.prefecture);
  document.querySelector("#prev-value").textContent = n(prev?.prefecture);
  document.querySelector("#prev2-value").textContent = n(prev2?.prefecture);

  const wow = prev?.prefecture ? ((latest.prefecture-prev.prefecture)/prev.prefecture)*100 : null;
  document.querySelector("#wow-value").textContent = wow===null ? "--" : `${wow>=0?"+":""}${n(wow,1)}%`;

  const [lv] = level(latest.prefecture);
  document.querySelector("#level-badge").textContent = lv;
  document.querySelector("#weekly-topic").textContent = cleanTopic(latest.topic);

  renderChart(weeks);
  renderComparison(weeks,latest);
  renderRanking(latest);
  renderMap(latest);
}

function renderChart(weeks){
  const labels = weeks.map(w=>w.label);
  const values = weeks.map(w=>w.prefecture);
  const ctx = document.querySelector("#trend-chart");
  new Chart(ctx,{
    type:"line",
    data:{
      labels,
      datasets:[{
        label:"県全体",
        data:values,
        borderColor:"#0b79b6",
        backgroundColor:"rgba(11,121,182,.10)",
        pointRadius:2.2,
        pointHoverRadius:5,
        borderWidth:2.3,
        tension:.22,
        fill:true
      }]
    },
    options:{
      responsive:true,
      maintainAspectRatio:false,
      interaction:{mode:"index",intersect:false},
      plugins:{
        legend:{display:false},
        tooltip:{
          callbacks:{
            label:(c)=>` 定点当たり ${n(c.raw)}`
          }
        }
      },
      scales:{
        x:{
          grid:{display:false},
          ticks:{maxRotation:0,autoSkip:true,maxTicksLimit:18,font:{size:10}}
        },
        y:{
          beginAtZero:true,
          grid:{color:"rgba(90,130,150,.12)"},
          title:{display:true,text:"定点当たり報告数"}
        }
      }
    }
  });

  requestAnimationFrame(()=>{
    const scroller=document.querySelector("#chart-scroll");
    scroller.scrollLeft=scroller.scrollWidth;
  });
  document.querySelector("#to-latest").addEventListener("click",()=>{
    const scroller=document.querySelector("#chart-scroll");
    scroller.scrollTo({left:scroller.scrollWidth,behavior:"smooth"});
  });
}

function renderComparison(weeks,latest){
  const target = weeks.find(w=>w.year===latest.year-1 && w.week===latest.week);
  document.querySelector("#this-period-label").textContent=`${latest.year} 第${latest.week}週`;
  document.querySelector("#this-period-value").textContent=n(latest.prefecture);

  if(!target){
    document.querySelector("#last-period-label").textContent=`${latest.year-1} 同週`;
    document.querySelector("#last-period-value").textContent="--";
    document.querySelector("#year-compare-note").textContent="前年同週データはまだ蓄積されていません。";
    return;
  }
  document.querySelector("#last-period-label").textContent=`${target.year} 第${target.week}週`;
  document.querySelector("#last-period-value").textContent=n(target.prefecture);
  const diff=latest.prefecture-target.prefecture;
  document.querySelector("#year-compare-note").textContent=
    `前年同週より ${diff>=0?"+":""}${n(diff)} ポイント。`;
}

function renderRanking(latest){
  const entries = Object.entries(latest.regions || {}).sort((a,b)=>b[1]-a[1]);
  const box=document.querySelector("#ranking");
  box.innerHTML="";
  entries.forEach(([name,value],i)=>{
    const row=document.createElement("div");
    row.className="rank-row";
    row.innerHTML=`<span class="rank-no">${i+1}</span><span class="rank-name">${name}</span><span class="rank-value">${n(value)}</span>`;
    box.appendChild(row);
  });
}

async function renderMap(latest){
  const map=L.map("map",{zoomControl:true,attributionControl:true}).setView([37.55,138.85],8);
  map.attributionControl.setPrefix(false);

  const geo=await fetch(GEOJSON_URL).then(r=>{
    if(!r.ok) throw new Error("GeoJSONを読み込めません");
    return r.json();
  });

  const layer=L.geoJSON(geo,{
    style:(feature)=>{
      const m=municipalityName(feature.properties||{});
      const region=regionForMunicipality(m);
      const v=region ? Number(latest.regions?.[region] ?? 0) : 0;
      return {
        color:"#ffffff",
        weight:1.1,
        fillColor:color(v),
        fillOpacity:.92
      };
    },
    onEachFeature:(feature,l)=>{
      const m=municipalityName(feature.properties||{});
      const region=regionForMunicipality(m);
      const v=region ? Number(latest.regions?.[region] ?? 0) : 0;
      l.bindTooltip(`<strong>${m}</strong><br>${region||"地域未対応"}${region?`：${n(v)}`:""}`,{sticky:true});
      l.on({
        mouseover:e=>e.target.setStyle({weight:2,color:"#3c6f86",fillOpacity:1}),
        mouseout:e=>layer.resetStyle(e.target)
      });
    }
  }).addTo(map);

  try{map.fitBounds(layer.getBounds(),{padding:[18,18]});}catch(e){}
}

main().catch(err=>{
  console.error(err);
  document.querySelector("#weekly-topic").textContent =
    "データの読み込みに失敗しました。data/influenza_history.json の配置を確認してください。";
});
