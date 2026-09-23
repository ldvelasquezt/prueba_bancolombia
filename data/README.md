# Datos

Los archivos crudos que entregó Bancolombia van en `raw/`. No los subo a git porque pesan
demasiado. Si clona este repo y no le aparecen, cópielos ahí antes de correr cualquier
pipeline.

## Lo que tiene que haber en `raw/`

| Archivo | Tamaño aprox. | Grano | Qué es |
|---|---|---|---|
| `Metadata.xlsx` | - | - | El diccionario de datos del banco |
| `prueba_op_base_pivot_var_rpta_alt_enmascarado_trtest.csv` | ~232 MB | cliente-obligación-mes | Histórico de train/test, con `var_rpta_alt` y las variables de gestión y opciones de pago |
| `prueba_op_base_pivot_var_rpta_alt_enmascarado_oot.csv` | ~3 MB | cliente-obligación-mes | La muestra out-of-time (enero de 2024) que hay que calificar, sin `var_rpta_alt` |
| `prueba_op_maestra_cuotas_pagos_mes_hist_enmascarado_completa.csv` | ~514 MB | cliente-obligación-mes | Cuotas y pagos mes a mes |
| `prueba_op_master_customer_data_enmascarado_completa.csv` | ~128 MB | cliente-mes | Datos demográficos y socioeconómicos |
| `prueba_op_probabilidad_oblig_base_hist_enmascarado_completa.csv` | ~390 MB | cliente-obligación-mes | Los scores que ya tiene el banco: `prob_propension`, `prob_alrt_temprana`, `prob_auto_cura` |
| `sample_submission.csv` | ~2.7 MB | cliente-obligación | El formato de entrega (`ID,var_rpta_alt`) |

## La llave para unir

`ID = nit_enmascarado#num_oblig_orig_enmascarado#num_oblig_enmascarado`

Ojo: hay tablas que solo traen `num_oblig_enmascarado`, sin el `_orig`. Sí es la misma
obligación, pero el mapeo quedó explícito en `build_dataset.py` para que nadie lo asuma.

## Las carpetas que se generan

- `interim/`: uniones y limpiezas intermedias. No va a git.
- `processed/`: los datasets finales listos para modelar. Tampoco va a git.
- `submissions/`: los `resultado_prueba.csv`. Estos sí, porque son el entregable.
