# Elliott Hybrid Scanner — 2026-10-05 17:13 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (1)

### PEPE/USDT — largo sobre `corrective_abc` (score 0.533, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-10-05 08:00 UTC (1 velas atrás)
- **Precio en la señal**: 0.0000
- **Zona de interés**: 0.0000 – 0.0000
- **Invalidación de la señal**: 0.0000

| factor | score | umbral | activo |
|---|---|---|---|
| fibonacci | 0.881 | 0.60 | ✅ |
| rsi_divergence | 0.000 | 0.60 | — |
| market_structure | 0.000 | 0.60 | — |
| volume_profile | 0.838 | 0.60 | ✅ |
| higher_timeframe_trend | 0.935 | 0.60 | ✅ |

<details><summary>detalle de factores</summary>

- **fibonacci**: precio 0.0000 sobre retroceso 0.618 en 0.0000
- **rsi_divergence**: sin divergencia alcista: precio 0.0000→0.0000, RSI 39.8→39.1
- **market_structure**: sin ruptura a favor de bullish: cierre 0.0000 contra referencia 0.0000
- **volume_profile**: vol B/A = 0.75; en un zigzag la B se seca
- **higher_timeframe_trend**: cierre 0.0000 contra EMA50 0.0000 (fuerza +0.87); señal bullish

> Tres tramos no permiten distinguir una corrección completa de un impulso en curso. Ambas lecturas se devuelven a propósito.

</details>

## Cerca del umbral (9)

La mejor estructura alcista vigente de cada par, re-evaluada al precio actual. NO son señales (les faltan factores): son los niveles a vigilar.

| par | hipótesis | score | factores activos | zona de compra | stop |
|---|---|---|---|---|---|
| DOT/USDT | `corrective_abc` | 0.365 | fibonacci, higher_timeframe_trend | 1.1768–1.2276 | 1.0780 |
| AVAX/USDT | `impulse_1_2_3` | 0.350 | volume_profile, higher_timeframe_trend | 13.0610–13.3859 | 10.8250 |
| SUI/USDT | `impulse_1_2_3` | 0.350 | volume_profile, higher_timeframe_trend | 1.2203–1.2797 | 0.8872 |
| ETH/USDT | `corrective_abc` | 0.350 | higher_timeframe_trend | 2,540.96–2,579.42 | 2,358.88 |
| LINK/USDT | `impulse_1_2_3` | 0.332 | volume_profile, higher_timeframe_trend | 13.9384–14.3584 | 12.6950 |
| BTC/USDT | `corrective_abc` | 0.331 | higher_timeframe_trend | 78,025.93–79,191.56 | 74,967.97 |
| BNB/USDT | `impulse_1_2_3` | 0.301 | volume_profile, higher_timeframe_trend | 839.41–851.69 | 773.76 |
| ADA/USDT | `impulse_1_2_3` | 0.281 | higher_timeframe_trend | 0.2796–0.2914 | 0.2623 |
| SOL/USDT | `impulse_1_2_3` | 0.275 | higher_timeframe_trend | 126.59–128.95 | 114.32 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
