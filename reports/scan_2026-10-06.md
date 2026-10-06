# Elliott Hybrid Scanner — 2026-10-06 18:28 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (1)

### PEPE/USDT — largo sobre `corrective_abc` (score 0.533, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-10-05 08:00 UTC (7 velas atrás)
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

## Cerca del umbral (10)

La mejor estructura alcista vigente de cada par, re-evaluada al precio actual. NO son señales (les faltan factores): son los niveles a vigilar.

| par | hipótesis | score | factores activos | zona de compra | stop |
|---|---|---|---|---|---|
| DOT/USDT | `corrective_abc` | 0.446 | fibonacci, higher_timeframe_trend | 1.1774–1.2269 | 1.0780 |
| AVAX/USDT | `impulse_1_2_3` | 0.350 | volume_profile, higher_timeframe_trend | 13.0559–13.3910 | 10.8250 |
| SUI/USDT | `impulse_1_2_3` | 0.350 | volume_profile, higher_timeframe_trend | 1.2242–1.2758 | 0.8872 |
| ETH/USDT | `corrective_abc` | 0.340 | higher_timeframe_trend | 2,541.20–2,579.18 | 2,358.88 |
| LINK/USDT | `impulse_1_2_3` | 0.332 | volume_profile, higher_timeframe_trend | 13.9618–14.3350 | 12.6950 |
| BTC/USDT | `corrective_abc` | 0.321 | higher_timeframe_trend | 78,031.45–79,186.04 | 74,967.97 |
| DOGE/USDT | `impulse_1_2_3` | 0.320 | volume_profile, higher_timeframe_trend | 0.0914–0.0937 | 0.0914 |
| BNB/USDT | `impulse_1_2_3` | 0.301 | volume_profile, higher_timeframe_trend | 840.29–850.82 | 773.76 |
| ADA/USDT | `impulse_1_2_3` | 0.271 | higher_timeframe_trend | 0.2795–0.2914 | 0.2623 |
| SOL/USDT | `impulse_1_2_3` | 0.265 | higher_timeframe_trend | 126.58–128.96 | 114.32 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
