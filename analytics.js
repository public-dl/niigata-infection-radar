// Google Analytics 4 - 新潟インフルエンザレーダー
// Measurement ID: G-F1R8PP684Q
(function () {
  'use strict';

  var MEASUREMENT_ID = 'G-F1R8PP684Q';

  // Prevent duplicate initialization if this script is included more than once.
  if (window.__niigataInfluenzaGa4Loaded) return;
  window.__niigataInfluenzaGa4Loaded = true;

  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () {
    window.dataLayer.push(arguments);
  };

  window.gtag('js', new Date());
  window.gtag('config', MEASUREMENT_ID);

  var script = document.createElement('script');
  script.async = true;
  script.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(MEASUREMENT_ID);
  document.head.appendChild(script);
})();
