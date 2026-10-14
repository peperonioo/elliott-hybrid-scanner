# Elliott Hybrid Scanner — 2026-10-14 23:18 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (1)

### BTC/USDT — largo sobre `corrective_abc` (score 0.458, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-10-13 12:00 UTC (7 velas atrás)
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
| XRP/USDT | `corrective_abc` | 0.521 | rsi_divergence, volume_profile | 1.3681–1.4011 | 1.3112 |
| DOGE/USDT | `corrective_abc` | 0.479 | rsi_divergence, volume_profile | 0.0837–0.0863 | 0.0800 |
| BNB/USDT | `corrective_abc` | 0.467 | fibonacci, volume_profile | 738.52–750.82 | 722.40 |
| ETH/USDT | `corrective_abc` | 0.449 | fibonacci, volume_profile | 2,487.40–2,541.87 | 2,409.09 |
| PEPE/USDT | `corrective_abc` | 0.430 | fibonacci, volume_profile | 0.0000–0.0000 | 0.0000 |
| SOL/USDT | `corrective_abc` | 0.407 | rsi_divergence, volume_profile | 107.25–110.60 | 101.69 |
| LINK/USDT | `corrective_abc` | 0.364 | volume_profile | 12.8064–13.2528 | 12.2590 |
| AVAX/USDT | `corrective_abc` | 0.302 | volume_profile, higher_timeframe_trend | 10.7800–11.1780 | 9.7640 |
| SUI/USDT | `corrective_abc` | 0.293 | volume_profile, higher_timeframe_trend | 1.1399–1.1868 | 0.9980 |
| DOT/USDT | `impulse_1_2_3` | 0.135 | higher_timeframe_trend | 1.4197–1.4741 | 1.2360 |
| ADA/USDT | `impulse_1_2_3` | 0.117 | — | 0.3059–0.3151 | 0.2654 |
| TRX/USDT | `diagonal_contracting` | 0.095 | — | 0.3330–0.3353 | 0.3301 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
