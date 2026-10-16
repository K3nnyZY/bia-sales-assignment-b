# Prueba real del proveedor — Sprint 3

Fecha: 2026-10-15. Seguimiento de la [verificación local](sprint-3-verification.md).

## Resultado real

La clave configurada en `.env` está disponible en el backend y fue aceptada
para consultar el modelo (`GET /v1/models/gpt-5.4-mini-2026-03-17`: HTTP 200).
El intento de generación real del agente mediante LangGraph/LiteLLM falló.
Un diagnóstico directo confirmó:

```json
{
  "status": 429,
  "error_code": "credit_balance_exhausted",
  "error_type": "insufficient_quota"
}
```

La [documentación oficial de OpenAI](https://developers.openai.com/api/docs/guides/error-codes)
indica que este código corresponde a falta de créditos prepagados y requiere
agregar créditos antes de reintentar. No es un problema que se resuelva
regenerando respuestas, cambiando de modo o repitiendo solicitudes en bucle.
No se realizaron más llamadas de generación después de confirmar ese código.

El gateway devolvió un error controlado, sin fallback determinista. Se conserva
la ejecución `run-82531fcdf19949058e12a848f8209c08`, modo `provider`, agente v2,
con **8 eventos** (`authorize → route → invoice → previous → knowledge →
calculate → generate → failure`) y tres tools completadas. El API muestra
`failed / MODEL_UNAVAILABLE`; no expone el mensaje privado del SDK. Tokens y
coste permanecen **null**, porque el proveedor no reportó uso en esta ejecución.
No se afirma una explicación exitosa de un LLM real.

La [evidencia JSON](sprint-3-provider-check.json) conserva la traza sanitizada,
los códigos y el resultado. No contiene claves ni tokens de autenticación.

## Configuración aplicada con autorización explícita

La primera solicitud de registrar y aprobar el modelo fue rechazada por la
revisión automática por tratarse de una ampliación persistente del catálogo.
Se solicitó autorización explícita al usuario para modelo, snapshot y grants;
el usuario la concedió y entonces se aplicó la configuración por los mecanismos
existentes, sin eludir controles del backend:

- Catálogo: `openai-gpt54-mini-20260317`, proveedor openai, snapshot exacto
  `gpt-5.4-mini-2026-03-17`, perfil advanced. Alta pending y aprobación mediante
  REST con la identidad administrator de demo.
- Definición revisable: [JSON del modelo](examples/openai-gpt54-mini.json).
  Los límites, capacidades y precios vienen de la
  [ficha oficial del modelo](https://developers.openai.com/api/docs/models/gpt-5.4-mini).
- Seed confiable: `billing-assistant` **v2**, snapshot con grants locales
  explícitos para demo-creator y demo-customer-b. La versión sintética v1
  permanece disponible. No se publica ninguna versión ni se cambia la
  autorización sobre facturas.
- `.env`: `ENABLE_PROVIDER_RUNTIME=true`; se conserva la clave local sin
  imprimirla ni copiarla al repositorio. API en 8001 y Playground en 3000.

## Repetir desde Terminal

Primero agrega créditos en la facturación de la organización API de la clave.
Después, desde la raíz del proyecto:

```sh
cd /Users/kennyzhu/Documents/bia-sales-assignment-b
make up
make provider-smoke
```

`make provider-smoke` hace una ejecución con proveedor mediante `/api/v1/runs`,
comprueba cálculo de Python, traza persistida y rechazo de factura ajena.
**Puede consumir saldo de API**. No registra modelos ni concede permisos.
Requiere un snapshot aprobado/configurado y grant existente; no se ejecuta
como parte de `make verify` o CI. Si no hay un modo proveedor disponible,
falla antes de intentar generar. Si el proveedor falla, imprime el run ID y
el error persistido y termina con código distinto de cero.

En este Mac ya quedaron preparados modelo y v2. En un entorno nuevo, un
administrador debe registrar/aprobar el JSON del modelo según README, y luego:

```sh
docker compose exec -T api python -m app.runtime.seed --model-id openai-gpt54-mini-20260317
```

Para repetir las pruebas sin llamadas reales al proveedor:

```sh
make verify
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
```

## Repetir desde Playground

1. Abre `http://localhost:3000/playground`.
2. Inicia sesión con el valor de `DEMO_CREATOR_TOKEN` de `.env`.
3. Selecciona **Billing Assistant · v2 · openai-gpt54-mini-20260317**.
4. Comprueba el modo **Proveedor · LiteLLM**. La ayuda aclara que el LLM solo
   ordena afirmaciones/citas verificadas; no redacta libremente ni calcula cargos.
5. Elige **Comparar con el mes anterior**, factura `INV-1002`, y escribe
   `Explica la diferencia de esta factura con agosto`.
6. Pulsa **Ejecutar agente**. Con el saldo todavía agotado se verá
   `failed / MODEL_UNAVAILABLE`; puedes consultar la traza del intento.
7. Cuando OpenAI permita generar, el criterio esperado es completed, diferencia
   **64.400 COP / 70 kWh**, fuentes autorizadas, nueve nodos y tres herramientas.
   Los tokens deben ser los reportados por SDK; el coste es una estimación con
   precios del snapshot. No se presenta este resultado esperado como ya probado.
8. Solicita `INV-2002` con el creator: debe denegarse antes de llamar al LLM.
9. Para seguir probando sin saldo, selecciona v1 y **Determinista · sin proveedor**.

## Comandos ejecutados

- `make up`: recreó API con credencial del servidor y flag habilitado; healthy.
- Consulta autenticada GET al modelo en OpenAI: HTTP 200, sin mostrar la clave.
- POST/PATCH administrativos locales para registrar/aprobar la definición.
- `docker compose exec -T api python -m app.runtime.seed --model-id openai-gpt54-mini-20260317`:
  v2 provisionada.
- `docker compose exec -T api python - < scripts/provider_smoke.py`: exit 1,
  run persisted failed / MODEL_UNAVAILABLE, sin fallback.
- Diagnóstico mínimo por LiteLLM: RateLimitError, HTTP 429.
- Diagnóstico HTTP directo con respuesta sanitizada: credit_balance_exhausted /
  insufficient_quota. No se volvieron a intentar generaciones después.
- Lectura de `/api/v1/runs/{id}/trace`: confirma persistencia y uso/coste nulos.

Se corrigió también el aislamiento de la fixture de integración: los flags y
claves reales del entorno no deben activar proveedores durante Pytest. El E2E
de catálogos ahora elige un perfil libre en lugar de asumir advanced disponible,
conservando intacta la aprobación del modelo real.

La generación exitosa del proveedor sigue pendiente de saldo. No se avanzó al
Sprint 4 ni se modificó el circuito de publicación/aprobación de agentes.

## Verificación final y archivos

- `make verify`: **exit 0**, 169 Pytest aprobadas, Ruff correcto (55 archivos),
  build/ESLint/TypeScript correctos, 13 tests frontend aprobados y smoke
  determinista completo aprobado. No se invocó el proveedor durante esta suite.
- `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e`: **3 passed** (3,6 s), con el
  catálogo real presente y ejecuciones de prueba deterministas.
- El primer `make test` con el flag del entorno habilitado detectó un caso
  dependiente del entorno (168 passed/1 failed). Se aisló la configuración de
  la fixture de test; la suite final quedó con 169 passed.
- `ruff check`, `ruff format --check`, `git diff --check`: correctos.
- La prueba real del proveedor permanece **fallida por saldo**, no aprobada.

Archivos añadidos: `scripts/provider_smoke.py`,
`docs/examples/openai-gpt54-mini.json`, `docs/sprint-3-provider-check.md` y `.json`.
Modificados: `Makefile`, `apps/api/tests/conftest.py`,
`tests/e2e/management.spec.ts`, `README.md`, `docs/sprint-3-report.md` y
`docs/sprint-3-verification.md`. `.env` se actualizó localmente y sigue ignorado.
No se guardaron secretos en los archivos de evidencia ni en el JSON del modelo.
