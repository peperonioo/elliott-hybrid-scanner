# Elliott Hybrid Scanner — 2026-09-16 13:34 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (1)

### XRP/USDT — largo sobre `corrective_abc` (score 0.525, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-09-14 08:00 UTC (12 velas atrás)
- **Precio en la señal**: 1.3987
- **Zona de interés**: 1.3811 – 1.4166
- **Invalidación de la señal**: 1.3150
- **Hipótesis alternativas**: `impulse_1_2_3` — el conteo es ambiguo

| factor | score | umbral | activo |
|---|---|---|---|
| fibonacci | 0.991 | 0.60 | ✅ |
| rsi_divergence | 0.659 | 0.60 | ✅ |
| market_structure | 0.000 | 0.60 | — |
| volume_profile | 0.000 | 0.60 | — |
| higher_timeframe_trend | 0.728 | 0.60 | ✅ |

<details><summary>detalle de factores</summary>

- **fibonacci**: precio 1.3987 sobre retroceso 0.618 en 1.3989
- **rsi_divergence**: divergencia alcista: precio 1.3781→1.3150, RSI 41.4→48.0
- **market_structure**: sin ruptura a favor de bullish: cierre 1.3412 contra referencia 1.4835
- **volume_profile**: vol B/A = 1.11; en un zigzag la B se seca
- **higher_timeframe_trend**: cierre 1.3412 contra EMA50 1.2772 (fuerza +0.46); señal bullish

> Tres tramos no permiten distinguir una corrección completa de un impulso en curso. Ambas lecturas se devuelven a propósito.

</details>

## Cerca del umbral (12)

La mejor estructura alcista vigente de cada par, re-evaluada al precio actual. NO son señales (les faltan factores): son los niveles a vigilar.

| par | hipótesis | score | factores activos | zona de compra | stop |
|---|---|---|---|---|---|
| PEPE/USDT | `corrective_abc` | 0.464 | rsi_divergence, volume_profile | 0.0000–0.0000 | 0.0000 |
| BNB/USDT | `corrective_abc` | 0.428 | volume_profile, higher_timeframe_trend | 703.43–717.13 | 674.60 |
| ETH/USDT | `impulse_1_2_3` | 0.313 | volume_profile, higher_timeframe_trend | 2,796.05–2,857.46 | 2,546.66 |
| TRX/USDT | `impulse_1_2_3` | 0.237 | volume_profile | 0.3484–0.3512 | 0.3411 |
| SOL/USDT | `corrective_abc` | 0.232 | higher_timeframe_trend | 102.56–105.00 | 98.0000 |
| SUI/USDT | `corrective_abc` | 0.198 | rsi_divergence | 0.7740–0.7992 | 0.6926 |
| DOGE/USDT | `impulse_1_2_3` | 0.183 | volume_profile | 0.1010–0.1033 | 0.0900 |
| DOT/USDT | `corrective_abc` | 0.161 | — | 0.7531–0.7903 | 0.7230 |
| AVAX/USDT | `corrective_abc` | 0.150 | higher_timeframe_trend | 7.7364–7.9432 | 7.2570 |
| BTC/USDT | `impulse_1_2_3` | 0.148 | higher_timeframe_trend | 85,364.51–86,695.99 | 81,478.87 |
| ADA/USDT | `impulse_1_2_3` | 0.139 | — | 0.2426–0.2500 | 0.2272 |
| LINK/USDT | `impulse_1_2_3` | 0.121 | higher_timeframe_trend | 15.2098–15.5926 | 12.6200 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
