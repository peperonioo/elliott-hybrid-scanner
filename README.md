# Elliott Hybrid Scanner

Scanner diario de señales para criptomonedas basado en un híbrido de Teoría de
Ondas de Elliott y confluencia técnica.

> **Este sistema no ejecuta órdenes.** Genera y rankea señales, nada más. Solo
> usa endpoints públicos de exchanges, sin API keys. Todo su output es
> informativo y está pensado para validarse después a mano en TradingView.

## Estado

| Fase | Módulo | Estado |
|------|--------|--------|
| 1 — Ingesta | `data/` | ✅ implementada |
| 2 — Detección de swings | `structure/` | ✅ implementada |
| 3 — Validador Elliott | `elliott/` | ✅ implementada |
| 4 — Capa de confluencia | `confluence/` | ✅ implementada |
| 5 — Backtest | `backtest/` | ✅ implementada |
| 6 — Reporte diario | `report/` | ✅ implementada |
| 7 — Automatización | `.github/` | ✅ implementada |

## Instalación

Requiere Python 3.12+.

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Uso

```bash
.venv/bin/python scripts/fetch_data.py
```

Opciones útiles:

```bash
.venv/bin/python scripts/fetch_data.py --bases BTC ETH --timeframes 4h
.venv/bin/python scripts/fetch_data.py --show BTC --rows 10
.venv/bin/python scripts/fetch_data.py --force-full
```

Los datos se cachean en `data/cache/<exchange>/<par>/<timeframe>.parquet`. Las
ejecuciones siguientes solo descargan las velas nuevas.

Detección de swings y validación visual:

```bash
.venv/bin/python scripts/plot_swings.py --bases BTC
.venv/bin/python scripts/plot_swings.py --bases BTC --compare 1.5 2.5 3.5 4.5
```

Escaneo de confluencia:

```bash
.venv/bin/python scripts/scan.py --explain
```

Backtest:

```bash
.venv/bin/python scripts/backtest.py --trades trades.csv
```

Informe diario (descarga las velas nuevas y escribe `reports/scan_<fecha>.md`):

```bash
.venv/bin/python scripts/daily_report.py
```

En GitHub, el workflow `daily-scan` lo hace solo cada día a las 00:20 UTC y
commitea el informe al repo. No necesita secretos.

## Fuente de datos

Binance es la fuente primaria de la serie de precios y Kraken el fallback. La
razón es concreta y está verificada: **el endpoint público de OHLC de Kraken
ignora el parámetro `since`** y devuelve siempre las últimas ~720 velas, sin
paginación hacia atrás. Eso limita su histórico a 4 meses en 4h y 30 días en
1h, insuficiente para el walk-forward de la fase 5.

```
kraken   BTC/USD   4h  since=2023-01-01 -> n= 721  first=2026-04-05
binance  BTC/USDT  4h  since=2023-01-01 -> n=1000  first=2022-12-31 (pagina)
```

Kraken sigue siendo la referencia de **comisiones** en el backtest.

## Resultados del backtest

Metodología: el periodo desde **2025-02-01 está reservado como holdout** y no
se tocó durante el desarrollo. Toda la exploración (ablación de entradas,
filtros y direcciones) se hizo con datos anteriores; el holdout se evaluó una
única vez al final.

Configuración final, justificada por ablación en desarrollo: entrada a
mercado, **solo largos**, objetivo 2R, cierre a 30 velas. La entrada limitada
en la zona de Fibonacci se descartó por selección adversa (cuando el precio no
vuelve a la zona es porque el movimiento es fuerte: la limitada se pierde los
mejores y se queda los flojos).

| | desarrollo (2022→2025-01) | **holdout (2025-02→2026-08)** |
|---|---|---|
| operaciones | 143 | **20** |
| esperanza neta/op. | +0,58% | **+0,66%** |
| profit factor | 1,23 | **1,30** |
| acierto | 43,4% | **55,0%** |
| retorno total | +52,6% | **+9,9%** |
| buy & hold del periodo | +32,7% | **−40,9%** |
| p contra azar | **0,035** | 0,183 |

Lectura honesta: la esperanza es positiva y consistente entre desarrollo y
holdout, y en desarrollo bate al azar de forma significativa. En el holdout la
dirección se mantiene pero **20 operaciones no dan potencia estadística**
(p=0,183): el resultado es prometedor, no probado. El sistema ganó un +9,9% en
un periodo en el que el mercado cayó un 40,9% de media.

Los costes se modelan por tipo de orden: taker+slippage+spread (0,34%/lado) en
ejecuciones agresivas, maker (0,16%) en limitadas. Al baseline aleatorio se le
imputa el mismo coste medio que pagó el sistema, para que el contraste mida la
señal y no la diferencia de comisiones.

El lado corto queda excluido: es coherente con operar spot sin margen y en
desarrollo rendía −0,73% por operación frente a +1,13% de los largos.

## Decisiones de diseño

**La vela en curso se descarta.** Una vela sin cerrar tiene un `close` que aún
se mueve. Si entrase en la caché, el ATR de la fase 2 y los indicadores de la
fase 4 se calcularían sobre un valor que en producción todavía no se conocía.
Es lookahead bias por la puerta de atrás, y por eso se corta en la ingesta y no
más adelante.

**Los swings no pueden mirar al futuro.** Un pivote se detecta en la vela de su
extremo, pero solo se puede *saber* más tarde: cuando el precio retrocede el
umbral y han cerrado `confirmation_bars` velas. Cada pivote lleva su
`confirmed_index`, y de ahí sale el invariante que se testea: ejecutar la
detección sobre `frame[:t+1]` da exactamente el mismo resultado que ejecutarla
sobre la serie completa y filtrar por `confirmed_index <= t`. Ligado a esto,
una reversión nunca se confirma en la misma vela que marca el extremo: con solo
OHLC no sabemos si dentro de la vela ocurrió antes el máximo o el mínimo, y
asumirlo sería inventarse información.

**Lo ambiguo se devuelve como ambiguo.** El validador de Elliott descarta, no
predice: responde "¿es este conteo estructuralmente posible?", nunca "¿cuál es
el conteo correcto?". Tres tramos de precio pueden ser una corrección A-B-C
completa o las ondas 1-2-3 de un impulso en curso, y no hay forma de saberlo
con la secuencia sola — así que se devuelven las dos lecturas marcadas como
ambiguas entre sí.

**Una diagonal no es un impulso con el solape perdonado.** Siguiendo la
formulación de Frost & Prechter, el solape de la onda 4 con la 1 es su rasgo
*definitorio* —obligatorio— y además la estructura tiene que ser una cuña, con
las longitudes variando de forma consistente (contractiva: 3<1, 5<3, 4<2). Sin
la exigencia de cuña, cualquier lateral de cinco piernas pasaba por diagonal:
sobre los 9 pares en 4H eso daba 724 diagonales frente a 260 impulsos, justo al
revés de lo que dice la literatura. Con la cuña quedan 89, y la proporción de
ventanas con algún conteo válido baja del 25% al 8,9%.

Las diagonales expansivas existen en la teoría pero son raras, así que vienen
desactivadas por defecto (`allow_expanding_diagonals`). El dato lo respalda:
activarlas añade 110 conteos, más que todas las contractivas juntas, lo que
indica que el patrón expansivo se satisface por accidente con facilidad.

**La dirección de la señal no es la del conteo.** Un impulso alcista
*completado* no es una señal alcista: es la antesala de la corrección. Lo mismo
con un A-B-C, que al terminar anticipa la reanudación de la tendencia previa. La
excepción es el impulso parcial 1-2-3, que sigue vivo y sí apunta a favor. La
especificación no lo fijaba y cambia el signo de todo el sistema.

**Emitir señal no es puntuar alto.** El score es la media ponderada de los cinco
factores, pero la condición de emisión es que al menos tres superen su propio
umbral. Un factor aislado en 1.0 no emite nada. Sobre 4.543 evaluaciones
históricas eso deja un 7,7% de conteos con señal, y nunca se activan los cinco
a la vez — señal de que los factores son de verdad independientes.

**La validación informa, no aborta.** Los huecos y las velas de volumen cero se
reportan pero no invalidan la serie por defecto: el cripto cotiza 24/7, pero
los exchanges tienen paradas de mantenimiento, y descartar cuatro años de datos
por un incidente de 2023 sería peor que anotarlo. La política es configurable
(`warn` / `raise` / `fix` / `drop`) y hay además un `max_gap_ratio` que sí
marca la serie como no apta cuando el deterioro es real.

**Cero valores en el código.** Todo lo ajustable vive en `config.yaml`.

## Configuración

`config.yaml` es la única fuente de verdad. Los parámetros más sensibles:

| Clave | Qué gobierna |
|-------|--------------|
| `history.start_date` | profundidad del histórico (la fase 5 pide ≥ 2 años) |
| `history.drop_incomplete_candle` | descarte de la vela sin cerrar |
| `validation.max_gap_ratio` | tolerancia a huecos antes de descartar un par |
| `swings.atr_threshold` | umbral del ZigZag en múltiplos de ATR (fase 2) |
| `confluence.min_active_factors` | factores mínimos para emitir señal (fase 4) |

## Desarrollo

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m black .
```

La suite no toca la red: los exchanges se sustituyen por dobles deterministas
en `tests/helpers.py`.

## Arquitectura

```
src/ehs/
  config.py          carga de config.yaml
  data/
    schema.py        esquema canónico de las series OHLCV
    gateway.py       ccxt, solo endpoints públicos: rate limit y reintentos
    cache.py         caché Parquet con escritura atómica
    fetcher.py       orquestación: descarga incremental + validación
    validation.py    huecos, duplicados, volumen cero, coherencia OHLC
  structure/
    indicators.py    ATR de Wilder, causal y estable ante prefijos
    swings.py        ZigZag con umbral en ATR, sin lookahead
    plotting.py      gráficos de validación visual
  elliott/
    validator.py     reglas duras, guías blandas e hipótesis ambiguas
  confluence/
    scorer.py        cinco factores independientes y regla de emisión
  backtest/
    engine.py        simulación de operaciones y modelo de costes
    metrics.py       métricas y distribución de resultados
    baselines.py     buy & hold y señales aleatorias
    walkforward.py   folds y selección del parámetro
  report/
    daily.py         informe diario en Markdown, mismo pipeline que el backtest
```
