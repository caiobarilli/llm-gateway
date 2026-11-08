# Operação

## `/health`

`GET /health` responde `200` com `{"status":"ok"}`, sem token. Ele não consulta o Ollama: `ok` quer dizer que o processo atende. Se o Ollama estiver fora, o `/health` continua `ok` e o chat responde 503 `upstream_indisponivel`.

A imagem declara o `HEALTHCHECK` com intervalo de 30 s, limite de 3 s, início de 5 s e 3 tentativas (`Dockerfile:57-58`). Ele chama o `/health` por dentro do container.

## Logs

Duas saídas:

- **stdout:** as linhas JSON do gateway, uma por evento.
- **stderr:** o log de inicialização do uvicorn, em texto (`Started server process`, `Application startup complete`).

Não há access log (`--no-access-log`).

### Linha de métricas do chat

Uma linha por pedido que chega à rota do chat, com sucesso ou erro. Um pedido recusado antes disso (token ausente, errado ou indisponível) não gera linha de chat, só o evento de autenticação.

```json
{"nivel": "info", "evento": "chat", "modelo": "llama3.2:3b", "status": 200, "codigo": null, "prompt_tokens": 63, "completion_tokens": 27, "tokens_por_segundo": 50.0, "carga_ms": 4, "duracao_ms": 1}
```

| Campo | Tipo | Significado |
|---|---|---|
| `nivel` | string | Nível do log. A linha do chat sai sempre em `info`. |
| `evento` | string | `chat`. |
| `modelo` | string ou `null` | O modelo do pedido, só depois de passar pela allowlist. É `null` quando o pedido foi recusado antes (corpo inválido, modelo fora da lista). |
| `status` | inteiro | O status HTTP da resposta. Exceção não prevista fica em 500. |
| `codigo` | string ou `null` | O `code` do erro (`docs/api.md`). `null` no sucesso. |
| `prompt_tokens` | inteiro ou `null` | `prompt_eval_count` do Ollama. `null` se o Ollama não chegou a responder. |
| `completion_tokens` | inteiro ou `null` | `eval_count` do Ollama. |
| `tokens_por_segundo` | número ou `null` | `eval_count` dividido por `eval_duration`, com uma casa decimal. `null` se não há duração. |
| `carga_ms` | inteiro ou `null` | Tempo de carga do modelo (`load_duration`), em ms. Alto na primeira chamada com o modelo frio. |
| `duracao_ms` | inteiro | Do começo da rota até o fim, em ms. Inclui a leitura do corpo e a chamada ao Ollama. |

Um erro depois da resposta do Ollama (`saida_invalida`, `saida_truncada`) já traz os tokens, a taxa e a carga:

```json
{"nivel": "info", "evento": "chat", "modelo": "llama3.2:3b", "status": 502, "codigo": "saida_invalida", "prompt_tokens": 63, "completion_tokens": 27, "tokens_por_segundo": 50.0, "carga_ms": 4, "duracao_ms": 1}
```

### Eventos de autenticação

Sem campos extras e sem valor do cabeçalho:

```json
{"nivel": "info", "evento": "autenticação recusada: token errado"}
```

Os motivos são `sem cabeçalho`, `cabeçalho malformado` e `token errado`. Quando o arquivo do token falha, o evento sai em `warning`: `token indisponível: <tipo do erro>` ou `token indisponível: arquivo vazio`.

## 503 ocupado

Com todas as vagas em uso, o pedido recebe 503 `ocupado` na hora, com `Retry-After: 10`. O gateway não guarda o pedido. Quem chama espera pelo menos esse tempo e tenta de novo. O valor é fixo e aproxima o tempo de um texto longo com o modelo carregado (ADR 0002).

## Tempos limite

| Trecho | Valor | Resposta ao estourar |
|---|---|---|
| Conexão com o Ollama | 5 s | 504 `upstream_timeout` |
| Leitura da resposta do Ollama | 60 s | 504 `upstream_timeout` |

O consumidor precisa esperar mais que isso. O `GeradorGateway` do PHParrot usa 90 s de leitura e 5 s de conexão (`rascunho-ia.md` do PHParrot). No PHParrot, medido com o `llama3.2:3b`, a carga a frio leva cerca de 10,5 s (ADR 0013 do PHParrot).

## O que o container espera de quem o roda

- **Token:** um arquivo legível pelo uid 10002, montado só leitura, e `GATEWAY_TOKEN_ARQUIVO` apontando para o caminho dentro do container. Para trocar o token, reescreva o arquivo no lugar. Trocar o inode de um arquivo montado sozinho (`mv`, editor) pode deixar o container com o valor antigo (ADR 0013 do PHParrot; não testado aqui).
- **Variáveis:** as quatro de `docs/configuracao.md`. Sem elas o container sai ao subir.
- **Porta:** o `EXPOSE 8000` não publica nada. Sem `-p`, a porta fica só na rede do container. Se publicar, só no loopback: `-p 127.0.0.1:8000:8000`.
- **Memória:** em repouso, sem pedidos, o container mediu cerca de 40 MiB com `docker stats`. Sob carga, não testado. Defina um limite (`--memory`).
- **Sistema de arquivos só leitura e `/tmp` em tmpfs:** testado com `--read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --memory 128m`. O container subiu, ficou `healthy` e respondeu 200 no `/health` e no `/v1/models`.
- **Ollama no host:** com Docker Engine, o nome `host.docker.internal` precisa de `--add-host=host.docker.internal:host-gateway`. No Docker Desktop ele existe (ADR 0013 do PHParrot; não testado aqui).

Exemplo completo:

```bash
docker run -d --name llm-gateway \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --memory 128m \
  -p 127.0.0.1:8000:8000 \
  --add-host=host.docker.internal:host-gateway \
  -v "$TOKEN_ARQUIVO:/token:ro" \
  -e GATEWAY_TOKEN_ARQUIVO=/token \
  -e GATEWAY_MODELOS=llama3.2:3b \
  -e GATEWAY_CONCORRENCIA=1 \
  -e GATEWAY_OLLAMA_URL=http://host.docker.internal:11434 \
  llm-gateway
```

## Falhas comuns

| Sintoma | Causa provável |
|---|---|
| O container sai ao subir | Variável `GATEWAY_*` ausente ou inválida. O erro cita o nome da variável. |
| 503 `token_indisponivel` | O arquivo do token não existe no container, está vazio, não é ASCII ou o uid 10002 não consegue lê-lo. |
| 503 `upstream_indisponivel` | O Ollama está fora do ar ou o endereço em `GATEWAY_OLLAMA_URL` não é alcançado de dentro do container. |
| 504 `upstream_timeout` | O Ollama não respondeu em 60 s, por exemplo com o modelo frio e a máquina ocupada. |
| 503 `ocupado` | Já há pedido em andamento. Espere o `Retry-After`. |
