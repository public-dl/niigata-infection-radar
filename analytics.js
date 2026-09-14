/*
  Google Analytics 4 loader
  1) Google Analytics で Web データストリームを作成
  2) 下の G-XXXXXXXXXX を実際の測定IDに置換
  3) このファイルをそのまま公開
*/
(() => {
  const MEASUREMENT_ID = "G-XXXXXXXXXX";

  // 未設定なら何も送信しない
  if (!/^G-[A-Z0-9]+$/i.test(MEASUREMENT_ID) || MEASUREMENT_ID === "G-XXXXXXXXXX") {
    console.info("Analytics is not configured. Set GA4 MEASUREMENT_ID in analytics.js.");
    return;
  }

  window.dataLayer = window.dataLayer || [];
  window.gtag = function(){ window.dataLayer.push(arguments); };

  const script = document.createElement("script");
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(MEASUREMENT_ID)}`;
  document.head.appendChild(script);

  window.gtag("js", new Date());
  window.gtag("config", MEASUREMENT_ID, {
    anonymize_ip: true
  });
})();
