# Elliott Hybrid Scanner — 2026-09-18 19:04 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (1)

### LINK/USDT — largo sobre `corrective_abc` (score 0.400, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-09-17 12:00 UTC (6 velas atrás)
- **Precio en la señal**: 11.3780
- **Zona de interés**: 11.2674 – 11.6352
- **Invalidación de la señal**: 10.6170
- **Hipótesis alternativas**: `impulse_1_2_3` — el conteo es ambiguo

| factor | score | umbral | activo |
|---|---|---|---|
| fibonacci | 0.601 | 0.60 | ✅ |
| rsi_divergence | 0.000 | 0.60 | — |
| market_structure | 0.000 | 0.60 | — |
| volume_profile | 0.776 | 0.60 | ✅ |
| higher_timeframe_trend | 0.664 | 0.60 | ✅ |

<details><summary>detalle de factores</summary>

- **fibonacci**: precio 11.3780 sobre retroceso 0.618 en 11.4513
- **rsi_divergence**: sin divergencia alcista: precio 11.1210→10.6170, RSI 42.0→40.3
- **market_structure**: sin ruptura a favor de bullish: cierre 11.0570 contra referencia 13.6850
- **volume_profile**: vol B/A = 0.77; en un zigzag la B se seca
- **higher_timeframe_trend**: cierre 11.0570 contra EMA50 10.6235 (fuerza +0.33); señal bullish

> Tres tramos no permiten distinguir una corrección completa de un impulso en curso. Ambas lecturas se devuelven a propósito.

</details>

## Cerca del umbral (12)

La mejor estructura alcista vigente de cada par, re-evaluada al precio actual. NO son señales (les faltan factores): son los niveles a vigilar.

| par | hipótesis | score | factores activos | zona de compra | stop |
|---|---|---|---|---|---|
| DOGE/USDT | `corrective_abc` | 0.530 | fibonacci, rsi_divergence | 0.0833–0.0856 | 0.0783 |
| BTC/USDT | `corrective_abc` | 0.461 | fibonacci, higher_timeframe_trend | 77,198.33–78,462.80 | 74,967.97 |
| SOL/USDT | `corrective_abc` | 0.451 | fibonacci, higher_timeframe_trend | 100.05–102.71 | 95.8200 |
| BNB/USDT | `corrective_abc` | 0.430 | fibonacci, higher_timeframe_trend | 720.93–733.78 | 704.29 |
| ADA/USDT | `corrective_abc` | 0.383 | fibonacci | 0.2162–0.2244 | 0.2091 |
| TRX/USDT | `corrective_abc` | 0.373 | fibonacci | 0.3387–0.3409 | 0.3351 |
| AVAX/USDT | `corrective_abc` | 0.372 | higher_timeframe_trend | 7.4549–7.6667 | 7.1690 |
| XRP/USDT | `corrective_abc` | 0.357 | rsi_divergence | 1.3733–1.4244 | 1.3150 |
| SUI/USDT | `diagonal_contracting` | 0.289 | fibonacci | 0.7194–0.7445 | 0.6730 |
| ETH/USDT | `corrective_abc` | 0.277 | higher_timeframe_trend | 2,488.50–2,545.82 | 2,358.88 |
| PEPE/USDT | `corrective_abc` | 0.228 | volume_profile, higher_timeframe_trend | 0.0000–0.0000 | 0.0000 |
| DOT/USDT | `impulse_1_2_3` | 0.218 | higher_timeframe_trend | 1.5523–1.6040 | 1.0320 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
