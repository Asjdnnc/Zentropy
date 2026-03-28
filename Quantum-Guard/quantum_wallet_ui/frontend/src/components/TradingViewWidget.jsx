// TradingViewWidget.jsx
import React, { useEffect, useRef, memo } from 'react';

function TradingViewWidget() {
  const container = useRef();

  useEffect(
    () => {
      // Clear container before injecting script to prevent duplicate widgets if re-rendered
      if (container.current) {
        container.current.innerHTML = '';
        
        // Setup inner divs explicitly since we cleared it
        const widgetDiv = document.createElement("div");
        widgetDiv.className = "tradingview-widget-container__widget";
        widgetDiv.style.height = "calc(100vh - 200px)"; // Make it fill the space height properly
        widgetDiv.style.width = "100%";
        container.current.appendChild(widgetDiv);

        const copyrightDiv = document.createElement("div");
        copyrightDiv.className = "tradingview-widget-copyright";
        copyrightDiv.innerHTML = `<a href="https://www.tradingview.com/symbols/STRKUSDC/?exchange=BINANCE" rel="noopener nofollow" target="_blank"><span className="blue-text">STRKUSDC rate</span></a><span className="trademark">&nbsp;by TradingView</span>`;
        container.current.appendChild(copyrightDiv);

        const script = document.createElement("script");
        script.src = "https://s3.tradingview.com/external-embedding/embed-widget-symbol-overview.js";
        script.type = "text/javascript";
        script.async = true;
        script.innerHTML = `
          {
            "lineWidth": 2,
            "lineType": 0,
            "chartType": "area",
            "fontColor": "rgb(106, 109, 120)",
            "gridLineColor": "rgba(242, 242, 242, 0.06)",
            "volumeUpColor": "rgba(34, 171, 148, 0.5)",
            "volumeDownColor": "rgba(247, 82, 95, 0.5)",
            "backgroundColor": "#0F0F0F",
            "widgetFontColor": "#DBDBDB",
            "upColor": "#22ab94",
            "downColor": "#f7525f",
            "borderUpColor": "#22ab94",
            "borderDownColor": "#f7525f",
            "wickUpColor": "#22ab94",
            "wickDownColor": "#f7525f",
            "colorTheme": "dark",
            "isTransparent": false,
            "locale": "en",
            "chartOnly": false,
            "scalePosition": "right",
            "scaleMode": "Normal",
            "fontFamily": "-apple-system, BlinkMacSystemFont, Trebuchet MS, Roboto, Ubuntu, sans-serif",
            "valuesTracking": "1",
            "changeMode": "price-and-percent",
            "symbols": [
              [
                "BINANCE:STRKUSDC|1D"
              ]
            ],
            "dateRanges": [
              "1d|1",
              "1m|30",
              "3m|60",
              "12m|1D",
              "60m|1W",
              "all|1M"
            ],
            "fontSize": "10",
            "headerFontSize": "medium",
            "autosize": true,
            "width": "100%",
            "height": "100%",
            "noTimeScale": false,
            "hideDateRanges": false,
            "hideMarketStatus": false,
            "hideSymbolLogo": false
          }`;
        container.current.appendChild(script);
      }
    },
    []
  );

  return (
    <div className="tradingview-widget-container h-full w-full" ref={container}>
    </div>
  );
}

export default memo(TradingViewWidget);
