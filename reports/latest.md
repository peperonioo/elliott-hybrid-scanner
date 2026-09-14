# Elliott Hybrid Scanner — 2026-09-14 15:05 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (1)

### XRP/USDT — largo sobre `corrective_abc` (score 0.525, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-09-14 08:00 UTC (0 velas atrás)
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

## Cerca del umbral (11)

La mejor estructura alcista vigente de cada par, re-evaluada al precio actual. NO son señales (les faltan factores): son los niveles a vigilar.

| par | hipótesis | score | factores activos | zona de compra | stop |
|---|---|---|---|---|---|
| TRX/USDT | `corrective_abc` | 0.401 | fibonacci, higher_timeframe_trend | 0.3386–0.3410 | 0.3351 |
| ETH/USDT | `corrective_abc` | 0.377 | fibonacci, higher_timeframe_trend | 2,491.34–2,541.71 | 2,405.85 |
| BNB/USDT | `corrective_abc` | 0.345 | volume_profile, higher_timeframe_trend | 704.21–716.34 | 674.60 |
| BTC/USDT | `impulse_1_2_3` | 0.336 | volume_profile, higher_timeframe_trend | 69,261.93–70,281.49 | 65,474.46 |
| LINK/USDT | `impulse_1_2_3` | 0.300 | volume_profile, higher_timeframe_trend | 10.3606–10.6844 | 9.7460 |
| AVAX/USDT | `impulse_1_2_3` | 0.265 | volume_profile | 6.9274–7.1147 | 6.8770 |
| PEPE/USDT | `corrective_abc` | 0.231 | volume_profile | 0.0000–0.0000 | 0.0000 |
| SOL/USDT | `impulse_1_2_3` | 0.210 | higher_timeframe_trend | 121.35–123.65 | 102.74 |
| DOGE/USDT | `impulse_1_2_3` | 0.208 | volume_profile | 0.1011–0.1032 | 0.0900 |
| DOT/USDT | `corrective_abc` | 0.200 | higher_timeframe_trend | 0.7521–0.7913 | 0.7230 |
| ADA/USDT | `impulse_1_2_3` | 0.171 | — | 0.2428–0.2498 | 0.2272 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
