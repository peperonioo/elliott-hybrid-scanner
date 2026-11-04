# Elliott Hybrid Scanner — 2026-11-04 19:53 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (1)

### BTC/USDT — largo sobre `corrective_abc` (score 0.469, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-11-04 12:00 UTC (0 velas atrás)
- **Precio en la señal**: 80,296.01
- **Zona de interés**: 79,747.05 – 81,293.87
- **Invalidación de la señal**: 75,736.38
- **Hipótesis alternativas**: `impulse_1_2_3` — el conteo es ambiguo

| factor | score | umbral | activo |
|---|---|---|---|
| fibonacci | 0.710 | 0.60 | ✅ |
| rsi_divergence | 0.692 | 0.60 | ✅ |
| market_structure | 0.000 | 0.60 | — |
| volume_profile | 0.809 | 0.60 | ✅ |
| higher_timeframe_trend | 0.156 | 0.60 | — |

<details><summary>detalle de factores</summary>

- **fibonacci**: precio 80,296.0100 sobre retroceso 0.786 en 80,520.4633
- **rsi_divergence**: divergencia alcista: precio 79,220.7400→75,736.3800, RSI 29.0→35.9
- **market_structure**: sin ruptura a favor de bullish: cierre 77,453.8600 contra referencia 84,898.0000
- **volume_profile**: vol B/A = 0.76; en un zigzag la B se seca
- **higher_timeframe_trend**: cierre 77,453.8600 contra EMA50 80,133.5019 (fuerza -0.69); señal bullish

> Tres tramos no permiten distinguir una corrección completa de un impulso en curso. Ambas lecturas se devuelven a propósito.

</details>

## Cerca del umbral (12)

La mejor estructura alcista vigente de cada par, re-evaluada al precio actual. NO son señales (les faltan factores): son los niveles a vigilar.

| par | hipótesis | score | factores activos | zona de compra | stop |
|---|---|---|---|---|---|
| SUI/USDT | `corrective_abc` | 0.506 | fibonacci, rsi_divergence | 0.8981–0.9270 | 0.8277 |
| LINK/USDT | `corrective_abc` | 0.330 | fibonacci, volume_profile | 11.4713–11.8846 | 10.6310 |
| PEPE/USDT | `impulse_1_2_3` | 0.316 | volume_profile, higher_timeframe_trend | 0.0000–0.0000 | 0.0000 |
| TRX/USDT | `corrective_abc` | 0.267 | volume_profile | 0.3276–0.3325 | 0.3274 |
| ADA/USDT | `corrective_abc` | 0.256 | volume_profile | 0.2088–0.2151 | 0.1820 |
| AVAX/USDT | `impulse` | 0.194 | fibonacci | 8.7399–9.0450 | 8.2770 |
| XRP/USDT | `corrective_abc` | 0.192 | volume_profile | 1.2644–1.2972 | 1.2420 |
| SOL/USDT | `corrective_abc` | 0.180 | — | 97.0773–99.9343 | 89.8600 |
| ETH/USDT | `corrective_abc` | 0.167 | volume_profile | 2,268.01–2,328.55 | 2,226.44 |
| DOT/USDT | `corrective_abc` | 0.157 | rsi_divergence | 1.0580–1.0928 | 0.8690 |
| DOGE/USDT | `corrective_abc` | 0.151 | volume_profile | 0.0785–0.0806 | 0.0774 |
| BNB/USDT | `corrective_abc` | 0.033 | — | 730.25–745.92 | 718.00 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
