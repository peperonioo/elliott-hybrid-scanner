# Elliott Hybrid Scanner — 2026-10-13 19:21 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (1)

### BTC/USDT — largo sobre `corrective_abc` (score 0.458, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-10-13 12:00 UTC (0 velas atrás)
- **Precio en la señal**: 83,434.57
- **Zona de interés**: 83,020.90 – 84,262.85
- **Invalidación de la señal**: 81,033.66

| factor | score | umbral | activo |
|---|---|---|---|
| fibonacci | 0.666 | 0.60 | ✅ |
| rsi_divergence | 0.000 | 0.60 | — |
| market_structure | 0.000 | 0.60 | — |
| volume_profile | 1.000 | 0.60 | ✅ |
| higher_timeframe_trend | 0.705 | 0.60 | ✅ |

<details><summary>detalle de factores</summary>

- **fibonacci**: precio 83,434.5700 sobre retroceso 0.786 en 83,641.8752
- **rsi_divergence**: sin divergencia alcista: precio 80,393.5600→81,033.6600, RSI 31.2→51.1
- **market_structure**: sin ruptura a favor de bullish: cierre 81,850.0000 contra referencia 87,395.6700
- **volume_profile**: vol B/A = 0.65; en un zigzag la B se seca
- **higher_timeframe_trend**: cierre 81,850.0000 contra EMA50 80,123.2145 (fuerza +0.41); señal bullish

> Tres tramos no permiten distinguir una corrección completa de un impulso en curso. Ambas lecturas se devuelven a propósito.

</details>

## Cerca del umbral (12)

La mejor estructura alcista vigente de cada par, re-evaluada al precio actual. NO son señales (les faltan factores): son los niveles a vigilar.

| par | hipótesis | score | factores activos | zona de compra | stop |
|---|---|---|---|---|---|
| DOGE/USDT | `corrective_abc` | 0.479 | rsi_divergence, volume_profile | 0.0837–0.0863 | 0.0800 |
| BNB/USDT | `corrective_abc` | 0.467 | fibonacci, volume_profile | 738.52–750.82 | 722.40 |
| ETH/USDT | `corrective_abc` | 0.449 | fibonacci, volume_profile | 2,487.40–2,541.87 | 2,409.09 |
| PEPE/USDT | `corrective_abc` | 0.430 | fibonacci, volume_profile | 0.0000–0.0000 | 0.0000 |
| SOL/USDT | `corrective_abc` | 0.407 | rsi_divergence, volume_profile | 107.25–110.60 | 101.69 |
| AVAX/USDT | `corrective_abc` | 0.367 | volume_profile, higher_timeframe_trend | 10.7981–11.1599 | 9.7640 |
| LINK/USDT | `corrective_abc` | 0.364 | volume_profile | 12.8064–13.2528 | 12.2590 |
| SUI/USDT | `corrective_abc` | 0.283 | volume_profile, higher_timeframe_trend | 1.1387–1.1879 | 0.9980 |
| DOT/USDT | `corrective_abc` | 0.236 | higher_timeframe_trend | 1.1456–1.2057 | 1.0780 |
| TRX/USDT | `corrective_abc` | 0.211 | — | 0.3366–0.3383 | 0.3318 |
| ADA/USDT | `impulse_1_2_3` | 0.109 | — | 0.3054–0.3156 | 0.2654 |
| XRP/USDT | `corrective_abc` | 0.060 | — | 1.4928–1.5295 | 1.3189 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
