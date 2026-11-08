# Configuração

O gateway lê quatro variáveis de ambiente ao subir (`Config.do_ambiente`, em `src/llm_gateway/config.py`). Nenhuma tem padrão: as quatro são obrigatórias.

| Variável | Obrigatória | Padrão | Formato | Erro quando está errada |
|---|---|---|---|---|
| `GATEWAY_TOKEN_ARQUIVO` | sim | nenhum | Caminho de um arquivo com o token, dentro do container. | `GATEWAY_TOKEN_ARQUIVO ausente` (variável ausente, vazia ou só espaços) |
| `GATEWAY_MODELOS` | sim | nenhum | Nomes separados por vírgula. Espaços ao redor são aparados e itens vazios são ignorados. | `GATEWAY_MODELOS vazio` |
| `GATEWAY_CONCORRENCIA` | sim | nenhum | Inteiro, no mínimo 1. | `GATEWAY_CONCORRENCIA precisa ser um inteiro` ou `GATEWAY_CONCORRENCIA precisa ser pelo menos 1` |
| `GATEWAY_OLLAMA_URL` | sim | nenhum | URL que começa com `http://` ou `https://`. A barra final é removida. | `GATEWAY_OLLAMA_URL precisa começar com http:// ou https://` |

## O que acontece com valor inválido

A `Config` é montada dentro do `criar_app`. Variável faltando ou inválida levanta `ConfiguracaoInvalida` e o processo termina antes de aceitar conexão. As mensagens de erro citam o nome da variável, nunca o valor.

## Detalhes por variável

**`GATEWAY_TOKEN_ARQUIVO`.** O gateway não confere se o arquivo existe ao subir. Ele o lê a cada pedido: arquivo ausente, ilegível, vazio, fora de ASCII ou com menos de 32 caracteres (depois do `strip`) dá 503 `token_indisponivel` (`docs/api.md`). Gere o token com `openssl rand -hex 32` (64 caracteres). O arquivo precisa ser legível pelo usuário do container (uid 10002). O token nunca vem de variável de ambiente.

**`GATEWAY_MODELOS`.** É a allowlist. A comparação é exata, com maiúsculas e minúsculas. A ordem da variável é a ordem do `GET /v1/models`. Modelo fora da lista dá 404 `model_not_found` e nunca chega ao Ollama.

**`GATEWAY_CONCORRENCIA`.** É o número de pedidos ao Ollama ao mesmo tempo. Com todas as vagas ocupadas, o pedido seguinte recebe 503 `ocupado`, sem fila.

**`GATEWAY_OLLAMA_URL`.** É a única base de URL que o gateway chama, e só em `POST /api/chat`. O pedido do cliente não escolhe o destino. Redirecionamentos não são seguidos.

## Valores fixos no código

Não há variável para estes. Mudar um deles é mudar o código.

| Valor | Constante | Onde |
|---|---|---|
| Corpo máximo de 64 KiB | `LIMITE_DO_CORPO` | `src/llm_gateway/chat.py:23` |
| Mensagens por pedido: 8 | `LIMITE_DE_MENSAGENS` | `src/llm_gateway/chat.py:24` |
| Caracteres por mensagem e somados: 8000 | `LIMITE_DE_CARACTERES` | `src/llm_gateway/chat.py:25` |
| `max_tokens` máximo: 1024 | `LIMITE_DE_TOKENS` | `src/llm_gateway/chat.py:26` |
| `max_tokens` padrão: 512 | `TOKENS_PADRAO` | `src/llm_gateway/chat.py:27` |
| Nome do modelo: 100 caracteres (mais que isso dá 400 `invalid_request`) | `LIMITE_DO_NOME` | `src/llm_gateway/modelos.py:4` |
| Conexão com o Ollama: 5 s | `TEMPO_DE_CONEXAO` | `src/llm_gateway/ollama.py:8` |
| Leitura do Ollama: 60 s | `TEMPO_DE_LEITURA` | `src/llm_gateway/ollama.py:9` |
| Contexto do modelo (`num_ctx`): 4096 | `CONTEXTO` | `src/llm_gateway/ollama.py:10` |
| `Retry-After` do 503: 10 s | `ESPERA_SUGERIDA_EM_SEGUNDOS` | `src/llm_gateway/concorrencia.py:7` |

## O servidor

A imagem sobe `uvicorn --factory llm_gateway.app:criar_app --host 0.0.0.0 --port 8000 --no-access-log --no-server-header` (`Dockerfile:70`). A porta 8000 é a do container. Publicá-la, e onde, é decisão de quem roda a imagem (`docs/operacao.md`).
