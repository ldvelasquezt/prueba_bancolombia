# Datos

Los archivos crudos entregados por Bancolombia van en `raw/` (no se versionan en git por
tamaño — ver `.gitignore`). Si clonas este repo sin los datos, cópialos manualmente ahí
antes de correr cualquier pipeline.

## Archivos esperados en `raw/`

| Archivo | Filas aprox. | Grano | Descripción |
|---|---|---|---|
| `Metadata.xlsx` | - | - | Diccionario de datos / metadata de columnas entregado por el banco |
| `prueba_op_base_pivot_var_rpta_alt_enmascarado_trtest.csv` | ~232 MB | cliente-obligación-mes | Histórico train/test con la variable respuesta `var_rpta_alt` y variables de gestión/opciones de pago |
| `prueba_op_base_pivot_var_rpta_alt_enmascarado_oot.csv` | ~3 MB | cliente-obligación-mes | Muestra out-of-time (enero 2024) a calificar — sin `var_rpta_alt` |
| `prueba_op_maestra_cuotas_pagos_mes_hist_enmascarado_completa.csv` | ~514 MB | cliente-obligación-mes | Histórico de cuotas y pagos mensuales |
| `prueba_op_master_customer_data_enmascarado_completa.csv` | ~128 MB | cliente-mes | Datos demográficos/socioeconómicos del cliente |
| `prueba_op_probabilidad_oblig_base_hist_enmascarado_completa.csv` | ~390 MB | cliente-obligación-mes | Scores existentes del banco: `prob_propension`, `prob_alrt_temprana`, `prob_auto_cura` |
| `sample_submission.csv` | ~2.7 MB | cliente-obligación | Formato de sumisión esperado (`ID,var_rpta_alt`) |

## Llave de unión

`ID = nit_enmascarado#num_oblig_orig_enmascarado#num_oblig_enmascarado` (algunas tablas
solo tienen `num_oblig_enmascarado`, sin el `_orig`; revisar en la etapa de preparación
de datos si son la misma obligación o requieren mapeo).

## Carpetas derivadas

- `interim/`: datos intermedios (uniones, limpieza) — no versionados.
- `processed/`: datasets finales de train/valid/test listos para modelar — no versionados.
- `submissions/`: archivos `resultado_prueba.csv` generados — sí versionados (son entregable).
